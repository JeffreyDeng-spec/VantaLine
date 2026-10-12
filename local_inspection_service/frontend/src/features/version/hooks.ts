import { useEffect, useRef, useSyncExternalStore } from "react";
import type { VersionParticipant } from "./coordinator";
import { versionCoordinator } from "./runtime";
export function useVersionState() { return useSyncExternalStore(versionCoordinator.subscribe, versionCoordinator.snapshot); }
export function useVersionParticipant(participant: VersionParticipant) {
  const current = useRef(participant);
  current.current = participant;
  useEffect(() => versionCoordinator.register({
    dirty: () => Boolean(current.current.dirty?.()),
    busy: () => Boolean(current.current.busy?.()),
    pause: () => current.current.pause?.(),
    cleanup: () => current.current.cleanup?.()
  }), []);
  useEffect(() => { versionCoordinator.signal(); });
}
