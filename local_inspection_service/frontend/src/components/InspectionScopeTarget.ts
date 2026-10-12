import { createContext, type Dispatch, type SetStateAction } from "react";

// Relocate the existing administrator control without duplicating its state or query.
export const InspectionScopeTarget = createContext<Dispatch<SetStateAction<HTMLElement | null>>>(() => {});
