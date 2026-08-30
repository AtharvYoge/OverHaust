import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const defaults: IconProps = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
};

export function LogoMark(props: IconProps) {
  return (
    <svg {...defaults} {...props} width={props.width ?? 22} height={props.height ?? 22}>
      <rect x="3" y="3" width="8" height="8" rx="2.5" fill="currentColor" stroke="none" opacity="0.9" />
      <rect x="13" y="3" width="8" height="8" rx="2.5" fill="currentColor" stroke="none" opacity="0.45" />
      <rect x="3" y="13" width="8" height="8" rx="2.5" fill="currentColor" stroke="none" opacity="0.45" />
      <rect x="13" y="13" width="8" height="8" rx="2.5" fill="currentColor" stroke="none" opacity="0.2" />
    </svg>
  );
}

export function HomeIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props}>
      <path d="M4 10.5 12 4l8 6.5V19a1.5 1.5 0 0 1-1.5 1.5H5.5A1.5 1.5 0 0 1 4 19v-8.5Z" />
      <path d="M9.5 20.5V13a2.5 2.5 0 0 1 5 0v7.5" />
    </svg>
  );
}

export function FolderIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props}>
      <path d="M4 7.5A1.5 1.5 0 0 1 5.5 6H9l2 2h7.5A1.5 1.5 0 0 1 20 9.5v7A1.5 1.5 0 0 1 18.5 18h-13A1.5 1.5 0 0 1 4 16.5v-9Z" />
    </svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props}>
      <path d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7A2.5 2.5 0 0 1 16.5 16H9l-4 3.5V16H7.5A2.5 2.5 0 0 1 5 13.5v-7Z" />
    </svg>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props}>
      <circle cx="12" cy="12" r="2.75" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4l1.4-1.4M17 7l1.4-1.4" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export function FlowArrowIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props} width={props.width ?? 16} height={props.height ?? 16}>
      <path d="M12 5v10M8 11l4 4 4-4" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props}>
      <path d="m5 12 14-7-4 14-2-5-8-2Z" />
    </svg>
  );
}

export function FolderOpenIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props} width={props.width ?? 40} height={props.height ?? 40} strokeWidth={1.5}>
      <path d="M4 9.5A1.5 1.5 0 0 1 5.5 8H9l2 2h8.5A1.5 1.5 0 0 1 21 11.5V17a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 5 17v-7.5Z" />
      <path d="M5 11h16" opacity="0.5" />
    </svg>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <svg {...defaults} {...props}>
      <path d="M12 3l1.2 4.2L17.5 8.5 13.2 9.7 12 14l-1.2-4.3L6.5 8.5l4.3-1.3L12 3Z" />
      <path d="M18 15l.6 2.1 2.1.6-2.1.6L18 20.4l-.6-2.1-2.1-.6 2.1-.6L18 15Z" opacity="0.55" />
    </svg>
  );
}
