"use client";
import { Component, ReactNode, useMemo, useRef, useSyncExternalStore } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, Float, Lightformer, useGLTF } from "@react-three/drei";
import * as THREE from "three";

const BUST_URL = "/models/marble_bust_01/marble_bust_01_2k.gltf";

/* The master's stroke: starts beside the bust's gaze, sweeps across the
   foreground and dives off the bottom edge — where the painted SVG thread
   in the page below picks it up. */
const STROKE_POINTS: [number, number, number][] = [
  [2.35, 0.55, -0.4],
  [1.5, 0.95, 0.2],
  [0.2, 0.75, 0.5],
  [-1.3, 0.15, 0.3],
  [-2.1, -0.75, 0.5],
  [-1.1, -1.55, 0.9],
  [0.15, -1.8, 1.1],
  [0.55, -2.9, 1.3],
];

/* Layered ribbons around one path = the ridged body of thick paint. */
const RIDGES = [
  { offset: 0.0,   radius: 0.15, color: "#b4511f", rough: 0.32 },
  { offset: 0.105, radius: 0.085, color: "#d96b2f", rough: 0.26 },
  { offset: -0.1,  radius: 0.075, color: "#8f3f18", rough: 0.38 },
];

const INTRO_TARGET = 0.72;   // how much of the stroke paints itself on load
const INTRO_SPEED = 0.55;    // eased approach rate

function makeCurve(offsetY: number) {
  return new THREE.CatmullRomCurve3(
    STROKE_POINTS.map(([x, y, z]) => new THREE.Vector3(x, y + offsetY, z)),
    false,
    "centripetal"
  );
}

function PaintStroke({ progress }: { progress: React.MutableRefObject<number> }) {
  const meshRefs = useRef<(THREE.Mesh | null)[]>([]);
  const brushRef = useRef<THREE.Group>(null);
  const capRef = useRef<THREE.Mesh>(null);

  const curves = useMemo(() => RIDGES.map(r => makeCurve(r.offset)), []);
  const geometries = useMemo(
    () =>
      RIDGES.map((r, i) => {
        const geo = new THREE.TubeGeometry(curves[i], 220, r.radius, 16, false);
        geo.scale(1, 0.6, 1); // flatten: a loaded flat brush, not a noodle
        return geo;
      }),
    [curves]
  );
  const indexCounts = useMemo(() => geometries.map(g => g.index!.count), [geometries]);

  const up = useMemo(() => new THREE.Vector3(0, 1, 0), []);
  const tangent = useMemo(() => new THREE.Vector3(), []);
  const tip = useMemo(() => new THREE.Vector3(), []);
  const quat = useMemo(() => new THREE.Quaternion(), []);

  useFrame(() => {
    const p = THREE.MathUtils.clamp(progress.current, 0.001, 1);
    geometries.forEach((geo, i) => {
      // TubeGeometry indices run along the path, so drawRange reveals the
      // stroke exactly as a brush would lay it down.
      const count = Math.floor((indexCounts[i] * p) / 6) * 6;
      geo.setDrawRange(0, count);
      const mesh = meshRefs.current[i];
      if (mesh) mesh.visible = count > 0;
    });

    // TubeGeometry samples the curve uniformly in parameter space (getPoint,
    // not getPointAt), so the brush must do the same to sit on the wet end.
    curves[0].getPoint(p, tip);
    const brush = brushRef.current;
    if (brush) {
      curves[0].getTangent(p, tangent);
      brush.position.set(tip.x, tip.y + 0.06, tip.z + 0.04);
      // Lean the handle back from the direction of travel, like a held brush
      quat.setFromUnitVectors(up, tangent.clone().negate().add(new THREE.Vector3(0.25, 1.15, 0.55)).normalize());
      brush.quaternion.slerp(quat, 0.25);
    }
    const cap = capRef.current;
    if (cap) cap.position.copy(tip);
  });

  return (
    <group>
      {RIDGES.map((r, i) => (
        <mesh key={i} ref={el => { meshRefs.current[i] = el; }} geometry={geometries[i]}>
          <meshPhysicalMaterial
            color={r.color}
            roughness={r.rough}
            clearcoat={1}
            clearcoatRoughness={0.25}
            sheen={0.4}
            sheenColor={"#ffd9b0"}
          />
        </mesh>
      ))}

      {/* Rounded blob of wet paint hiding the tube's open end */}
      <mesh ref={capRef} scale={[1.15, 0.72, 1.15]}>
        <sphereGeometry args={[0.16, 20, 20]} />
        <meshPhysicalMaterial color="#b4511f" roughness={0.3} clearcoat={1} clearcoatRoughness={0.25} />
      </mesh>

      {/* The brush laying the stroke down */}
      <group ref={brushRef}>
        {/* bristles, tipped in paint */}
        <mesh position={[0, 0.09, 0]}>
          <coneGeometry args={[0.075, 0.3, 20]} />
          <meshStandardMaterial color="#8a6a3c" roughness={0.9} />
        </mesh>
        <mesh position={[0, -0.02, 0]}>
          <sphereGeometry args={[0.08, 16, 16]} />
          <meshPhysicalMaterial color="#b4511f" roughness={0.25} clearcoat={1} />
        </mesh>
        {/* ferrule */}
        <mesh position={[0, 0.3, 0]}>
          <cylinderGeometry args={[0.055, 0.075, 0.16, 20]} />
          <meshStandardMaterial color="#c8c2b4" roughness={0.25} metalness={0.9} />
        </mesh>
        {/* handle */}
        <mesh position={[0, 0.85, 0]}>
          <cylinderGeometry args={[0.035, 0.055, 0.95, 20]} />
          <meshStandardMaterial color="#5d4630" roughness={0.55} />
        </mesh>
      </group>

      {/* Fresh squeezed pigment resting where the stroke begins */}
      <mesh position={[2.5, 0.42, -0.3]} scale={[1, 0.45, 1]}>
        <sphereGeometry args={[0.16, 24, 24]} />
        <meshPhysicalMaterial color="#c9932e" roughness={0.28} clearcoat={1} />
      </mesh>
      <mesh position={[2.72, 0.36, -0.05]} scale={[1, 0.4, 1]}>
        <sphereGeometry args={[0.1, 24, 24]} />
        <meshPhysicalMaterial color="#3e5c76" roughness={0.28} clearcoat={1} />
      </mesh>
    </group>
  );
}

function Bust() {
  const { scene } = useGLTF(BUST_URL);
  const ref = useRef<THREE.Group>(null);

  const prepared = useMemo(() => {
    scene.traverse(obj => {
      if ((obj as THREE.Mesh).isMesh) {
        const mesh = obj as THREE.Mesh;
        mesh.castShadow = true;
        const mat = mesh.material as THREE.MeshStandardMaterial;
        if (mat) mat.envMapIntensity = 0.9;
      }
    });
    return scene;
  }, [scene]);

  useFrame((state, dt) => {
    const g = ref.current;
    if (!g) return;
    // The sculptor considers his work: a slow, living turn toward the stroke
    const target = -0.55 + state.pointer.x * 0.12 + Math.sin(state.clock.elapsedTime * 0.25) * 0.04;
    g.rotation.y = THREE.MathUtils.damp(g.rotation.y, target, 1.2, dt);
    g.rotation.x = THREE.MathUtils.damp(g.rotation.x, state.pointer.y * -0.04, 1.2, dt);
  });

  return (
    <group ref={ref} position={[2.05, -1.9, -1.1]} scale={4.4}>
      <primitive object={prepared} />
    </group>
  );
}

function Scene({ reduced }: { reduced: boolean }) {
  const progress = useRef(reduced ? 1 : 0);
  const group = useRef<THREE.Group>(null);

  useFrame((state, dt) => {
    if (!reduced) {
      // Paint the intro portion on load, then let scroll finish the stroke
      const scroll = Math.min(window.scrollY / Math.max(window.innerHeight, 1), 1);
      const target = INTRO_TARGET + (1 - INTRO_TARGET) * scroll;
      progress.current = THREE.MathUtils.damp(progress.current, target, INTRO_SPEED * 2.2, dt);

      const g = group.current;
      if (g) {
        g.rotation.y = THREE.MathUtils.damp(g.rotation.y, state.pointer.x * 0.05, 2, dt);
        g.position.y = THREE.MathUtils.damp(g.position.y, scroll * 1.1, 2, dt);
      }
    }
  });

  return (
    <group ref={group}>
      <Bust />
      <PaintStroke progress={progress} />

      <ContactShadows position={[0, -2.55, 0]} opacity={0.32} scale={14} blur={2.6} far={3.4} color="#4a3a24" />

      {/* Bright north-light studio: warm key, cool bounce — the temperature
          principle the app teaches, now in white */}
      <ambientLight intensity={0.85} color="#fff8ec" />
      <directionalLight position={[4, 6, 5]} intensity={1.6} color="#ffedd2" />
      <directionalLight position={[-6, 2, 4]} intensity={0.55} color="#cfdcea" />

      <Environment resolution={256} frames={1}>
        <Lightformer intensity={1.6} color="#fffaf0" position={[0, 5, 0]} rotation={[Math.PI / 2, 0, 0]} scale={[10, 10, 1]} />
        <Lightformer intensity={1.1} color="#ffe9c9" position={[5, 1, 4]} scale={[6, 4, 1]} />
        <Lightformer intensity={0.7} color="#d7e2ee" position={[-5, 0, 3]} scale={[5, 4, 1]} />
      </Environment>

      <Float speed={0.8} rotationIntensity={0.15} floatIntensity={0.4}>
        <mesh position={[-2.9, 1.7, -2.4]} scale={[1, 0.5, 1]}>
          <sphereGeometry args={[0.22, 24, 24]} />
          <meshPhysicalMaterial color="#9d2f2f" roughness={0.3} clearcoat={1} />
        </mesh>
      </Float>
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

useGLTF.preload(BUST_URL);

export default function AtelierHero() {
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
          camera={{ position: [0, 0, 6.2], fov: 40 }}
          dpr={[1, 1.5]}
          gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        >
          <Scene reduced={reduced} />
        </Canvas>
      </CanvasErrorBoundary>
      {/* Feather the studio into the paper page */}
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse at 62% 42%, transparent 42%, var(--bg) 96%)" }}
      />
    </div>
  );
}
