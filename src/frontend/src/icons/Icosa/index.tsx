import type React from "react";
import { forwardRef } from "react";
import SvgIcosa from "./Icosa";

export const IcosaIcon = forwardRef<SVGSVGElement, React.PropsWithChildren<{}>>(
  (props, ref) => {
    return <SvgIcosa ref={ref} {...props} />;
  },
);
