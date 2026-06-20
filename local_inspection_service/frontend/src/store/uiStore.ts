import { create } from "zustand";

interface UiState {
  dataUserId: string;
  setDataUserId: (userId: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  dataUserId: "",
  setDataUserId: (dataUserId) => set({ dataUserId })
}));
