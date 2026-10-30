import type { SVGProps } from "react";

/**
 * The icon set, 24 x 24 outline strokes (Lucide shapes). One file so every icon shares
 * the same weight. Size with `className="size-4"`; decorative by default.
 */
type Props = SVGProps<SVGSVGElement>;

function Svg({ children, ...props }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const BedIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M2 4v16" />
    <path d="M2 8h18a2 2 0 0 1 2 2v10" />
    <path d="M2 17h20" />
    <path d="M6 8v9" />
  </Svg>
);

export const BathIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M9 6 6.5 3.5a1.5 1.5 0 0 0-1-.5C4.683 3 4 3.683 4 4.5V17a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5" />
    <line x1="10" x2="8" y1="5" y2="7" />
    <line x1="2" x2="22" y1="12" y2="12" />
    <line x1="7" x2="7" y1="19" y2="21" />
    <line x1="17" x2="17" y1="19" y2="21" />
  </Svg>
);

export const RulerIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z" />
    <path d="m14.5 12.5 2-2" />
    <path d="m11.5 9.5 2-2" />
    <path d="m8.5 6.5 2-2" />
    <path d="m17.5 15.5 2-2" />
  </Svg>
);

export const CarIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2" />
    <circle cx="7" cy="17" r="2" />
    <path d="M9 17h6" />
    <circle cx="17" cy="17" r="2" />
  </Svg>
);

export const LandIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M3 21h18" />
    <path d="M5 21V7l8-4v18" />
    <path d="M19 21V11l-6-4" />
    <path d="M9 9v.01M9 12v.01M9 15v.01M9 18v.01" />
  </Svg>
);

export const HomeIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <path d="M9 22V12h6v10" />
  </Svg>
);

export const BuildingIcon = (p: Props) => (
  <Svg {...p}>
    <rect width="16" height="20" x="4" y="2" rx="2" ry="2" />
    <path d="M9 22v-4h6v4" />
    <path d="M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01" />
  </Svg>
);

export const SearchIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </Svg>
);

export const MapIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M14.1 6.2a1 1 0 0 1 .8 0l5.5 2.3a1 1 0 0 1 .6.9v10.1a1 1 0 0 1-1.4.9L15 18.4l-6 2.4-5.4-2.3a1 1 0 0 1-.6-.9V7.5a1 1 0 0 1 1.4-.9L9 8.5Z" />
    <path d="M15 6.4v12M9 8.5v12" />
  </Svg>
);

export const ListIcon = (p: Props) => (
  <Svg {...p}>
    <rect width="7" height="7" x="3" y="3" rx="1" />
    <rect width="7" height="7" x="14" y="3" rx="1" />
    <rect width="7" height="7" x="14" y="14" rx="1" />
    <rect width="7" height="7" x="3" y="14" rx="1" />
  </Svg>
);

export const ChevronDownIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
);

export const ChevronLeftIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m15 18-6-6 6-6" />
  </Svg>
);

export const ChevronRightIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m9 18 6-6-6-6" />
  </Svg>
);

export const ArrowLeftIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m12 19-7-7 7-7" />
    <path d="M19 12H5" />
  </Svg>
);

export const ArrowUpRightIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M7 7h10v10" />
    <path d="M7 17 17 7" />
  </Svg>
);

export const SparklesIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M9.9 2.7a.5.5 0 0 1 .9 0l1.5 4.1a4 4 0 0 0 2.4 2.4l4.1 1.5a.5.5 0 0 1 0 .9l-4.1 1.5a4 4 0 0 0-2.4 2.4l-1.5 4.1a.5.5 0 0 1-.9 0l-1.5-4.1a4 4 0 0 0-2.4-2.4L1.9 11.6a.5.5 0 0 1 0-.9l4.1-1.5a4 4 0 0 0 2.4-2.4Z" />
    <path d="M20 3v4M22 5h-4" />
  </Svg>
);

export const CheckIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M20 6 9 17l-5-5" />
  </Svg>
);

export const XIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Svg>
);

export const InfoIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 16v-4M12 8h.01" />
  </Svg>
);

export const GridIcon = (p: Props) => (
  <Svg {...p}>
    <rect width="18" height="18" x="3" y="3" rx="2" />
    <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
  </Svg>
);

export const ImagesIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M18 22H4a2 2 0 0 1-2-2V6" />
    <path d="m22 13-1.3-1.3a2 2 0 0 0-2.8 0L11 18" />
    <circle cx="12" cy="8" r="2" />
    <rect width="16" height="16" x="6" y="2" rx="2" />
  </Svg>
);

export const PinIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
    <circle cx="12" cy="10" r="3" />
  </Svg>
);

export const TrendIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M22 7 13.5 15.5 8.5 10.5 2 17" />
    <path d="M16 7h6v6" />
  </Svg>
);

export const HammerIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m15 12-8.4 8.4a2.1 2.1 0 1 1-3-3L12 9" />
    <path d="m17.6 9.6 2.4-2.4a1 1 0 0 0 0-1.4l-3.8-3.8a1 1 0 0 0-1.4 0L12.4 4.4" />
    <path d="m10.7 7.3 6 6" />
  </Svg>
);

export const KeyIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="7.5" cy="15.5" r="5.5" />
    <path d="m21 2-9.6 9.6" />
    <path d="m15.5 7.5 3 3L22 7l-3-3" />
  </Svg>
);

export const LayersIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m12.8 2.2 8.6 4a1 1 0 0 1 0 1.8l-8.6 4a2 2 0 0 1-1.7 0l-8.6-4a1 1 0 0 1 0-1.8l8.6-4a2 2 0 0 1 1.7 0Z" />
    <path d="m2 12 8.7 4a2 2 0 0 0 1.7 0L21 12" />
    <path d="m2 17 8.7 4a2 2 0 0 0 1.7 0L21 17" />
  </Svg>
);

export const HeartIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z" />
  </Svg>
);
