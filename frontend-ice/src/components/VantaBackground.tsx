import { useEffect, useRef } from 'react';

export default function VantaBackground() {
  const vantaRef = useRef<HTMLDivElement>(null);
  const vantaEffect = useRef<any>(null);

  useEffect(() => {
    let cancelled = false;
    let pollId: any = null;

    const init = () => {
      if (cancelled || vantaEffect.current || !vantaRef.current) return false;
      const VANTA = (window as any).VANTA;
      if (!VANTA || !VANTA.TOPOLOGY) return false;
      vantaEffect.current = VANTA.TOPOLOGY({
        el: vantaRef.current,
        mouseControls: true,
        touchControls: true,
        gyroControls: false,
        minHeight: 200.00,
        minWidth: 200.00,
        scale: 1.00,
        scaleMobile: 1.00,
        color: 0x00ffff, // Vibrant cyan for the topology lines
        backgroundColor: 0x1a0a2a, // Deep dark purple background
      });
      return true;
    };

    // The Vanta/p5 scripts load async from a CDN, so window.VANTA is often
    // not ready on first mount. Poll until it appears, then stop.
    if (!init()) {
      pollId = setInterval(() => {
        if (init() && pollId) { clearInterval(pollId); pollId = null; }
      }, 200);
    }

    return () => {
      cancelled = true;
      if (pollId) clearInterval(pollId);
      if (vantaEffect.current) {
        vantaEffect.current.destroy();
        vantaEffect.current = null;
      }
    };
  }, []);

  return <div ref={vantaRef} id="vanta-background" />;
}
