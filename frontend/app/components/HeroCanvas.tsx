"use client";
import { Component, ReactNode, useRef, useSyncExternalStore } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Environment, Float, Lightformer, MeshDistortMaterial, Sparkles } from "@react-three/drei";
import * as THREE from "three";

const BLOBS: { pos: [number, number, number]; r: number; color: string; speed: number; distort: number }[] = [
  { pos: [-3.4, 1.3, -2.2], r: 1.15, color: "#dca55e", speed: 1.1, distort: 0.45 },
  { pos: [3.5, -0.9, -3.0], r: 1.5,  color: "#bf5b45", speed: 0.8, distort: 0.35 },
  { pos: [2.7, 1.9, -1.6],  r: 0.7,  color: "#7d92ab", speed: 1.4, distort: 0.5 },
  { pos: [-2.5, -1.7, -1.2],r: 0.85, color: "#8a9179", speed: 1.2, distort: 0.4 },
  { pos: [0.3, -2.4, -2.6], r: 1.0,  color: "#e9ddc8", speed: 0.9, distort: 0.3 },
];

function Scene() {
  const group = useRef<THREE.Group>(null);

  useFrame((state, dt) => {
    const g = group.current;
    if (!g) return;
    const scroll = window.scrollY / window.innerHeight;
    const targetX = state.pointer.y * 0.12 + scroll * 0.3;
    const targetY = state.pointer.x * 0.2;
    g.rotation.x = THREE.MathUtils.damp(g.rotation.x, targetX, 3, dt);
    g.rotation.y = THREE.MathUtils.damp(g.rotation.y, targetY, 3, dt);
    g.position.y = THREE.MathUtils.damp(g.position.y, scroll * 1.4, 3, dt);
  });

  return (
    <group ref={group}>
      {BLOBS.map((b, i) => (
        <Float key={i} speed={b.speed} rotationIntensity={0.6} floatIntensity={1.2}>
          <mesh position={b.pos}>
            <sphereGeometry args={[b.r, 48, 48]} />
            <MeshDistortMaterial color={b.color} distort={b.distort} speed={1.6} roughness={0.35} metalness={0.05} />
          </mesh>
        </Float>
      ))}

      {/* Golden centrepiece — a polished brush-swirl knot catching the env light */}
      <Float speed={0.7} rotationIntensity={0.9} floatIntensity={0.8}>
        <mesh position={[1.7, 0.7, -0.6]} rotation={[0.5, 0.3, 0.1]}>
          <torusKnotGeometry args={[0.5, 0.16, 180, 28]} />
          <meshStandardMaterial color="#d9a05b" roughness={0.18} metalness={0.85} envMapIntensity={1.4} />
        </mesh>
      </Float>

      <Sparkles count={70} scale={12} size={2} speed={0.3} opacity={0.35} color="#f2c078" />

      {/* Warm key light vs cool fill — the colour-temperature principle the app teaches.
          decay=0 keeps classic falloff-free lighting so the blobs stay luminous. */}
      <ambientLight intensity={0.55} />
      <pointLight position={[5, 4, 5]} intensity={1.7} decay={0} color="#ffb36b" />
      <pointLight position={[-6, -2, 3]} intensity={0.9} decay={0} color="#7d92ab" />
      <fog attach="fog" args={["#0b0908", 8, 17]} />

      {/* Procedural environment (no HDR download) — gives the glass and blobs
          something warm/cool to reflect and refract */}
      <Environment resolution={256} frames={1}>
        <Lightformer intensity={2.2} color="#ffb36b" position={[4, 2, 4]} scale={[7, 3, 1]} />
        <Lightformer intensity={1.1} color="#7d92ab" position={[-5, -1, 3]} scale={[6, 3, 1]} />
        <Lightformer intensity={0.9} color="#f2e6d0" position={[0, 5, -2]} rotation={[Math.PI / 2, 0, 0]} scale={[9, 4, 1]} />
      </Environment>
    </group>
  );
}

class CanvasErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

const noopSubscribe = () => () => {};

export default function HeroCanvas() {
  // Server snapshot says "reduced" so SSR/hydration renders nothing; the real
  // client value takes over after mount without a setState-in-effect cycle.
  const reduced = useSyncExternalStore(
    noopSubscribe,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true
  );

  if (reduced) return null;

  return (
    <div id="hero-canvas" className="fixed inset-0 z-0 pointer-events-none">
      <CanvasErrorBoundary>
        <Canvas
          camera={{ position: [0, 0, 6], fov: 42 }}
          dpr={[1, 1.5]}
          gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        >
          <Scene />
        </Canvas>
      </CanvasErrorBoundary>
      {/* Soften the scene into the page background */}
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse at 50% 40%, transparent 30%, var(--bg) 95%)" }}
      />
    </div>
  );
}
