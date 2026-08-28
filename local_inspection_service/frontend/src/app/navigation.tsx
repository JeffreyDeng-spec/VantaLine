import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Box,
  Columns3,
  Database,
  LayoutDashboard,
  ScanLine,
  ScanText,
  Settings,
  Sparkles,
  Users
} from "lucide-react";

export interface NavItem {
  label: string;
  path: string;
  view: string;
  permission?: string;
  icon: LucideIcon;
  phase: "phase-1" | "phase-2" | "phase-3";
}

export interface NavGroup {
  label?: string;
  items: NavItem[];
}

export const overviewNavItem: NavItem = {
  label: "总览",
  path: "/",
  view: "home",
  icon: LayoutDashboard,
  phase: "phase-1"
};

export const detectionCenterNavItem: NavItem = {
  label: "检测中心",
  path: "/inspect",
  view: "inspect",
  permission: "ai_detection",
  icon: ScanLine,
  phase: "phase-3"
};

export const textCompareBetaNavItem: NavItem = {
  label: "文字对比 Beta",
  path: "/text-compare-beta",
  view: "textCompareBeta",
  permission: "inspection",
  icon: ScanText,
  phase: "phase-3"
};

export const dataAnalysisNavItem: NavItem = {
  label: "数据分析",
  path: "/data-analysis",
  view: "dataAnalysis",
  permission: "inspection",
  icon: BarChart3,
  phase: "phase-3"
};

export const systemNavItems: NavItem[] = [
  {
    label: "设置",
    path: "/rules",
    view: "rules",
    permission: "system_settings",
    icon: Settings,
    phase: "phase-2"
  },
  {
    label: "用户管理",
    path: "/users",
    view: "userManagement",
    permission: "user_management",
    icon: Users,
    phase: "phase-2"
  }
];

export const trainingAssetNavItems: NavItem[] = [
  {
    label: "配件库",
    path: "/accessories",
    view: "accessories",
    permission: "accessory_library",
    icon: Box,
    phase: "phase-3"
  },
  {
    label: "任务库",
    path: "/training-library?tab=tasks",
    view: "taskLibrary",
    permission: "model_library",
    icon: Database,
    phase: "phase-2"
  },
  {
    label: "样本与数据集",
    path: "/training-library?tab=datasets",
    view: "trainingDatasets",
    permission: "model_library",
    icon: Database,
    phase: "phase-2"
  },
  {
    label: "模型库",
    path: "/training-library?tab=models",
    view: "trainingLibrary",
    permission: "model_library",
    icon: Database,
    phase: "phase-2"
  },
  {
    label: "任务流水线",
    path: "/pipeline",
    view: "pipeline",
    permission: "training_pipeline",
    icon: Columns3,
    phase: "phase-3"
  }
];

export const hiddenToolNavItems: NavItem[] = [
  {
    label: "AI 检测",
    path: "/ai-inspect",
    view: "aiInspect",
    permission: "ai_detection",
    icon: Sparkles,
    phase: "phase-3"
  }
];

export const fixedNavItems = [overviewNavItem, detectionCenterNavItem, textCompareBetaNavItem, dataAnalysisNavItem, ...systemNavItems];

export const navGroups: NavGroup[] = [
  { items: [overviewNavItem, detectionCenterNavItem, textCompareBetaNavItem] },
  { label: "训练与资产", items: trainingAssetNavItems },
  { items: [dataAnalysisNavItem] },
  { label: "系统", items: systemNavItems }
];

export const navItems = [
  overviewNavItem,
  detectionCenterNavItem,
  textCompareBetaNavItem,
  dataAnalysisNavItem,
  ...systemNavItems,
  ...trainingAssetNavItems,
  ...hiddenToolNavItems
];
