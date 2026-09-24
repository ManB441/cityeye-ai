import { useEffect, useRef, useState } from "react";

export function useReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!media) return;
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return reduced;
}

/** One sleeping RAF loop, DOM-only pointer updates, and cached layout measurements. */
export function useCityEyeMotion(reduced: boolean) {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = root.current;
    const finePointer = window.matchMedia?.("(hover: hover) and (pointer: fine) and (min-width: 761px)");
    if (!element || !finePointer) return;
    let frame = 0;
    let active = false;
    let previous = 0;
    let x = 0, y = 0, targetX = 0, targetY = 0;
    let pointerX = -10_000, pointerY = -10_000;
    let centerX = 0, centerY = 0;
    let regions: { node: HTMLElement | SVGElement; x: number; y: number }[] = [];
    const enabled = () => !reduced && finePointer.matches && !document.hidden;
    const measure = () => {
      const eye = element.querySelector(".cityeye-visual")?.getBoundingClientRect();
      if (eye) { centerX = eye.left + eye.width / 2; centerY = eye.top + eye.height / 2; }
      const svg = element.querySelector(".city-network")?.getBoundingClientRect();
      if (svg) regions = Array.from(element.querySelectorAll<SVGElement>("[data-city-region]")).map(node => ({
        node, x: svg.left + Number(node.dataset.x) * svg.width / 1200,
        y: svg.top + Number(node.dataset.y) * svg.height / 900,
      }));
    };
    const draw = (time: number) => {
      frame = 0;
      if (!enabled()) return;
      const dt = previous ? Math.min(time - previous, 50) : 16;
      previous = time;
      const ease = 1 - Math.exp(-dt / 110);
      x += (targetX - x) * ease; y += (targetY - y) * ease;
      element.style.setProperty("--look-x", `${x.toFixed(2)}px`);
      element.style.setProperty("--look-y", `${y.toFixed(2)}px`);
      element.style.setProperty("--eye-x", `${(x * .34).toFixed(2)}px`);
      element.style.setProperty("--eye-y", `${(y * .34).toFixed(2)}px`);
      element.style.setProperty("--city-x", `${(-x * .17).toFixed(2)}px`);
      element.style.setProperty("--city-y", `${(-y * .17).toFixed(2)}px`);
      element.style.setProperty("--look-angle", `${(x * 1.2).toFixed(2)}deg`);
      for (const region of regions) {
        const near = active ? Math.max(0, 1 - Math.hypot(pointerX - region.x, pointerY - region.y) / 200) : 0;
        region.node.style.setProperty("--near", near.toFixed(3));
      }
      if (Math.abs(targetX - x) + Math.abs(targetY - y) > .02) frame = requestAnimationFrame(draw);
      else previous = 0;
    };
    const wake = () => { if (!frame && enabled()) frame = requestAnimationFrame(draw); };
    const move = (event: PointerEvent) => {
      if (!enabled() || event.pointerType === "touch") return;
      active = true; pointerX = event.clientX; pointerY = event.clientY;
      const dx = pointerX - centerX, dy = pointerY - centerY;
      const distance = Math.hypot(dx, dy);
      const offset = Math.min(14, distance / 24);
      targetX = distance ? dx / distance * offset : 0;
      targetY = distance ? dy / distance * offset : 0;
      wake();
    };
    const leave = () => { active = false; targetX = targetY = 0; wake(); };
    const reset = () => {
      cancelAnimationFrame(frame); frame = 0; previous = 0;
      x = y = targetX = targetY = 0; active = false;
      for (const key of ["--look-x", "--look-y", "--eye-x", "--eye-y", "--city-x", "--city-y"]) element.style.setProperty(key, "0px");
      element.style.setProperty("--look-angle", "0deg");
      for (const region of regions) region.node.style.setProperty("--near", "0");
      measure();
    };
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    observer?.observe(element);
    window.addEventListener("pointermove", move, { passive: true });
    document.documentElement.addEventListener("pointerleave", leave);
    window.addEventListener("blur", leave);
    window.addEventListener("scroll", measure, { passive: true });
    document.addEventListener("visibilitychange", reset);
    finePointer.addEventListener("change", reset);
    return () => {
      reset(); observer?.disconnect();
      window.removeEventListener("pointermove", move);
      document.documentElement.removeEventListener("pointerleave", leave);
      window.removeEventListener("blur", leave);
      window.removeEventListener("scroll", measure);
      document.removeEventListener("visibilitychange", reset);
      finePointer.removeEventListener("change", reset);
    };
  }, [reduced]);
  return root;
}
