import { create } from "zustand";

interface AppState {
  selectedJobId: number | null;
  setSelectedJobId: (jobId: number | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedJobId: null,
  setSelectedJobId: (selectedJobId) => set({ selectedJobId }),
}));
