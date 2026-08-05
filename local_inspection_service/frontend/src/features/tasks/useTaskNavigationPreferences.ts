import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getTaskNavigationPreferences, queryKeys, saveTaskNavigationPreferences } from "../../api/queries";
import type { TaskNavigationPreferences } from "../../api/types";
import {
  ARCHIVED_TASK_IDS_KEY,
  PINNED_TASK_IDS_KEY,
  claimLegacyTaskPreferences,
  clearClaimedLegacyTaskPreferences,
  writeStoredTaskIdsForUser
} from "../../utils/taskNavigation";

interface TaskPreferenceMutationVariables {
  userId: string;
  preferences: Pick<TaskNavigationPreferences, "pinned_task_ids" | "archived_task_ids">;
  clearsLegacy?: boolean;
}

export interface TaskPreferenceValues {
  pinnedTaskIds: string[];
  archivedTaskIds: string[];
}

export type TaskPreferenceUpdate = TaskPreferenceValues | ((current: TaskPreferenceValues) => TaskPreferenceValues);

function normalizeTaskPreferenceIds(ids: string[]) {
  return Array.from(new Set(ids.filter(Boolean)));
}

function sameTaskPreferenceValues(
  current: TaskNavigationPreferences | undefined,
  expected: TaskPreferenceMutationVariables["preferences"]
) {
  return (
    JSON.stringify(current?.pinned_task_ids ?? []) === JSON.stringify(expected.pinned_task_ids) &&
    JSON.stringify(current?.archived_task_ids ?? []) === JSON.stringify(expected.archived_task_ids)
  );
}

export function useTaskNavigationPreferences(userId: string, onSaveError?: (error: unknown) => void) {
  const queryClient = useQueryClient();
  const migratedLocalPreferencesRef = useRef(false);
  const activeUserIdRef = useRef(userId);
  const preferenceValuesRef = useRef<TaskPreferenceValues>({ pinnedTaskIds: [], archivedTaskIds: [] });
  activeUserIdRef.current = userId;
  const [pinnedTaskIds, setPinnedTaskIds] = useState<string[]>([]);
  const [archivedTaskIds, setArchivedTaskIds] = useState<string[]>([]);
  const taskPreferencesKey = queryKeys.taskNavigationPreferences(userId);
  const taskPreferencesQuery = useQuery({
    queryKey: taskPreferencesKey,
    queryFn: getTaskNavigationPreferences,
    enabled: Boolean(userId)
  });

  const taskPreferencesMutation = useMutation({
    scope: { id: "task-navigation-preferences" },
    mutationFn: (variables: TaskPreferenceMutationVariables) => {
      if (activeUserIdRef.current !== variables.userId) {
        return Promise.reject(new Error("Task preference save cancelled after account change"));
      }
      return saveTaskNavigationPreferences(variables.preferences);
    },
    onSuccess: (preferences, variables) => {
      const completedKey = queryKeys.taskNavigationPreferences(variables.userId);
      const current = queryClient.getQueryData<TaskNavigationPreferences>(completedKey);
      if (variables.clearsLegacy) clearClaimedLegacyTaskPreferences(variables.userId);
      // A newer optimistic write may already be queued. Do not let this older
      // response temporarily roll the UI/cache back and become the basis of a
      // subsequent user action.
      if (!sameTaskPreferenceValues(current, variables.preferences)) return;
      queryClient.setQueryData<TaskNavigationPreferences>(completedKey, preferences);
      if (activeUserIdRef.current === variables.userId) {
        mirrorTaskPreferences(variables.userId, preferences.pinned_task_ids, preferences.archived_task_ids);
      }
    },
    onError: (error, variables) => {
      const failedKey = queryKeys.taskNavigationPreferences(variables.userId);
      const current = queryClient.getQueryData<TaskNavigationPreferences>(failedKey);
      if (sameTaskPreferenceValues(current, variables.preferences)) {
        void queryClient.invalidateQueries({ queryKey: failedKey });
      }
      if (activeUserIdRef.current === variables.userId) onSaveError?.(error);
    }
  });

  useEffect(() => {
    activeUserIdRef.current = userId;
    migratedLocalPreferencesRef.current = false;
    preferenceValuesRef.current = { pinnedTaskIds: [], archivedTaskIds: [] };
    setPinnedTaskIds([]);
    setArchivedTaskIds([]);
    return () => {
      if (activeUserIdRef.current === userId) activeUserIdRef.current = "";
    };
  }, [userId]);

  useEffect(() => {
    const preferences = taskPreferencesQuery.data;
    if (!preferences) return;
    if (!migratedLocalPreferencesRef.current) {
      migratedLocalPreferencesRef.current = true;
      const legacy = claimLegacyTaskPreferences(userId);
      if (preferences.exists === false && (legacy.pinnedTaskIds.length || legacy.archivedTaskIds.length)) {
        persistTaskPreferences(
          { pinnedTaskIds: legacy.pinnedTaskIds, archivedTaskIds: legacy.archivedTaskIds },
          legacy.claimed
        );
        return;
      }
      if (legacy.claimed && preferences.exists !== false) clearClaimedLegacyTaskPreferences(userId);
    }
    mirrorTaskPreferences(userId, preferences.pinned_task_ids, preferences.archived_task_ids);
  }, [taskPreferencesQuery.data, userId]);

  function mirrorTaskPreferences(storageUserId: string, pinnedIds: string[], archivedIds: string[]) {
    const nextPinnedIds = normalizeTaskPreferenceIds(pinnedIds);
    const nextArchivedIds = normalizeTaskPreferenceIds(archivedIds);
    if (activeUserIdRef.current === storageUserId) {
      preferenceValuesRef.current = { pinnedTaskIds: nextPinnedIds, archivedTaskIds: nextArchivedIds };
      setPinnedTaskIds(nextPinnedIds);
      setArchivedTaskIds(nextArchivedIds);
    }
    writeStoredTaskIdsForUser(PINNED_TASK_IDS_KEY, storageUserId, nextPinnedIds);
    writeStoredTaskIdsForUser(ARCHIVED_TASK_IDS_KEY, storageUserId, nextArchivedIds);
  }

  function persistTaskPreferences(update: TaskPreferenceUpdate, clearsLegacy = false) {
    const requested = typeof update === "function" ? update(preferenceValuesRef.current) : update;
    const nextPinnedIds = normalizeTaskPreferenceIds(requested.pinnedTaskIds);
    const nextArchivedIds = normalizeTaskPreferenceIds(requested.archivedTaskIds);
    const nextPreferences: TaskNavigationPreferences = {
      pinned_task_ids: nextPinnedIds,
      archived_task_ids: nextArchivedIds,
      updated_at: Math.floor(Date.now() / 1000),
      exists: true
    };
    queryClient.setQueryData<TaskNavigationPreferences>(taskPreferencesKey, nextPreferences);
    mirrorTaskPreferences(userId, nextPinnedIds, nextArchivedIds);
    taskPreferencesMutation.mutate({
      userId,
      preferences: { pinned_task_ids: nextPinnedIds, archived_task_ids: nextArchivedIds },
      clearsLegacy
    });
  }

  return {
    pinnedTaskIds,
    archivedTaskIds,
    preferencesExist: Boolean(taskPreferencesQuery.data?.exists),
    preferencesReady: taskPreferencesQuery.isSuccess,
    isSavingPreferences: taskPreferencesMutation.isPending,
    persistTaskPreferences
  };
}
