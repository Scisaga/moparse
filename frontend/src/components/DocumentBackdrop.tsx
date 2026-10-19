/** Static document paths keep the header quiet and independent of canvas or animation. */
export function DocumentBackdrop() {
  return (
    <svg className="header-document" viewBox="0 0 1440 96" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1">
        <path className="document-connection" d="M340 48h72m76 0h80q18 0 18-18V17h114m-114 31v30h114m93-30h115m87 0h100" />
        <g className="document-sheet">
          <rect x="412" y="13" width="76" height="70" rx="8" />
          <path d="M428 30h33m-33 10h43m-43 10h43m-43 10h22" />
          <rect x="700" y="-16" width="93" height="64" rx="8" />
          <path d="M716 2h61m-61 10h41m-41 10h51" />
          <rect x="700" y="59" width="93" height="57" rx="8" />
          <path d="M716 76h61m-61 10h41m-41 10h51" />
          <rect x="908" y="16" width="87" height="64" rx="8" />
          <path d="M924 31h55v33h-55zm0 11h55m-55 11h55m-37-22v33m19-33v33" />
        </g>
      </g>
      <g className="document-node" fill="currentColor">
        <circle cx="340" cy="48" r="3" />
        <circle cx="586" cy="48" r="3" />
        <circle cx="1095" cy="48" r="3" />
      </g>
    </svg>
  )
}
