import { useId, type SVGProps } from 'react';

export function VeraIcon({
  size = 24,
  ...props
}: SVGProps<SVGSVGElement> & {
  size?: number | string;
}) {
  const maskId = useId();

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <mask id={maskId}>
        <rect width="24" height="24" fill="white" />

        <path
          d="M7.25 9.25H9.55L12 15.15L14.45 9.25H16.75L13.15 17.5C12.95 17.96 12.51 18.25 12 18.25C11.49 18.25 11.05 17.96 10.85 17.5L7.25 9.25Z"
          fill="black"
        />

        <path
          d="M14 2V7.25C14 7.664 14.336 8 14.75 8H20"
          stroke="black"
          strokeWidth="1"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </mask>

      <path
        mask={`url(#${maskId})`}
        fill="currentColor"
        d="M6 2H14L20 8V20C20 21.105 19.105 22 18 22H6C4.895 22 4 21.105 4 20V4C4 2.895 4.895 2 6 2Z"
      />
    </svg>
  );
}
