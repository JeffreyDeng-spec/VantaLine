import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Box,
  Columns3,
  Crosshair,
  Database,
  LayoutDashboard,
  ScanLine,
  Settings,
  Sparkles,
  Tags,
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

export const navGroups: NavGroup[] = [
  {
    items: [
      {
        label: "总览",
        path: "/",
        view: "home",
        icon: LayoutDashboard,
        phase: "phase-1"
      }
    ]
  },
  {
    label: "检测中心",
    items: [
      {
        label: "检测工作台",
        path: "/inspect",
        view: "inspect",
        permission: "inspection",
        icon: ScanLine,
        phase: "phase-3"
      },
      {
        label: "AI 检测",
        path: "/ai-inspect",
        view: "aiInspect",
        permission: "ai_detection",
        icon: Sparkles,
        phase: "phase-3"
      },
      {
        label: "标签匹配",
        path: "/label-sheet",
        view: "labelSheet",
        permission: "label_sheet",
        icon: Tags,
        phase: "phase-3"
      },
      {
        label: "开放定位",
        path: "/locate-anything",
        view: "locateAnything",
        permission: "locate_anything",
        icon: Crosshair,
        phase: "phase-3"
      }
    ]
  },
  {
    label: "资产与训练",
    items: [
      {
        label: "配件库",
        path: "/accessories",
        view: "accessories",
        permission: "accessory_library",
        icon: Box,
        phase: "phase-3"
      },
      {
        label: "数据分析",
        path: "/data-analysis",
        view: "dataAnalysis",
        permission: "ai_detection",
        icon: BarChart3,
        phase: "phase-3"
      },
      {
        label: "训练流水线",
        path: "/pipeline",
        view: "pipeline",
        permission: "training_pipeline",
        icon: Columns3,
        phase: "phase-3"
      },
      {
        label: "训练库",
        path: "/training-library",
        view: "trainingLibrary",
        permission: "model_library",
        icon: Database,
        phase: "phase-2"
      }
    ]
  },
  {
    label: "系统",
    items: [
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
    ]
  }
];

export const navItems = navGroups.flatMap((group) => group.items);
