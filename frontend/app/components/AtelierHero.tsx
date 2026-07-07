"use client";
import { Component, ReactNode, useMemo, useRef, useSyncExternalStore } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, Float, Lightformer, useGLTF } from "@react-three/drei";
import * as THREE from "three";

const BUST_URL = "/models/marble_bust_01/marble_bust_01_2k.gltf";

/* The master's stroke: a single smooth sweep down the gap between the
   headline and the bust, off the bottom edge — where the painted SVG thread
   in the page below picks it up. A gentle S, no zigzag. Forward in z so it
   reads in front of the bust. */
const STROKE_POINTS: [number, number, number][] = [
  [0.78, 1.85, 1.25],
  [1.05, 0.75, 1.3],
  [0.82, -0.5, 1.32],
  [1.05, -1.75, 1.34],
  [0.84, -3.0, 1.36],
  [0.98, -3.9, 1.38],
];

const STROKE_COLOR = "#b4511f";
const STROKE_EDGE = "#8f3f18";
const HALF_WIDTH = 0.11;      // widest half-width of the loaded brush
const DOME = 0.055;           // how far the ridge lifts toward camera (impasto)
const SAMPLES = 260;

const INTRO_TARGET = 0.72;   // how much of the stroke paints itself on load
const INTRO_SPEED = 0.55;    // eased approach rate

const STROKE_CURVE = new THREE.CatmullRomCurve3(
  STROKE_POINTS.map(([x, y, z]) => new THREE.Vector3(x, y, z)),
  false,
  "centripetal"
);

/* A real brushstroke is a flat, loaded ribbon: thin where the brush touches
   down, full through the body, tapering off the lifted end — with a raised
   central ridge so it catches light like wet impasto. TubeGeometry can't
   taper, so we build the ribbon by hand: three rows (left / raised centre /
   right) swept along the curve, ordered start→end so drawRange paints it. */
function buildStrokeGeometry(): THREE.BufferGeometry {
  const view = new THREE.Vector3(0, 0, 1); // camera looks down -z
  const side = new THREE.Vector3();
  const tan = new THREE.Vector3();
  const p = new THREE.Vector3();

  const pos: number[] = [];
  const idx: number[] = [];

  for (let i = 0; i < SAMPLES; i++) {
    const t = i / (SAMPLES - 1);
    STROKE_CURVE.getPoint(t, p);
    STROKE_CURVE.getTangent(t, tan);
    side.crossVectors(tan, view).normalize();

    // width envelope: quick touch-down, full body, tapered lift-off
    const touch = Math.min(1, t / 0.06);
    const lift = 1 - Math.pow(Math.max(0, (t - 0.72) / 0.28), 1.5);
    const w = HALF_WIDTH * touch * Math.max(0.05, lift);
    const dome = DOME * touch * Math.max(0.05, lift);

    // left, centre(raised toward camera), right
    pos.push(p.x - side.x * w, p.y - side.y * w, p.z - side.z * w);
    pos.push(p.x, p.y, p.z + dome);
    pos.push(p.x + side.x * w, p.y + side.y * w, p.z + side.z * w);

    if (i > 0) {
      const a = (i - 1) * 3;
      const b = i * 3;
      // left quad
      idx.push(a, a + 1, b, a + 1, b + 1, b);
      // right quad
      idx.push(a + 1, a + 2, b + 1, a + 2, b + 2, b + 1);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  return geo;
}

function PaintStroke({ progress }: { progress: React.MutableRefObject<number> }) {
  const strokeRef = useRef<THREE.Mesh>(null);
  const edgeRef = useRef<THREE.Mesh>(null);
  const brushRef = useRef<THREE.Group>(null);

  const geo = useMemo(() => buildStrokeGeometry(), []);
  const edgeGeo = useMemo(() => geo.clone(), [geo]);
  const totalIdx = geo.index!.count;

  const up = useMemo(() => new THREE.Vector3(0, 1, 0), []);
  const tangent = useMemo(() => new THREE.Vector3(), []);
  const tip = useMemo(() => new THREE.Vector3(), []);
  const quat = useMemo(() => new THREE.Quaternion(), []);

  useFrame(() => {
    const p = THREE.MathUtils.clamp(progress.current, 0.0, 1);
    // indices are ordered start→end, 12 per segment; reveal proportionally
    const count = Math.floor((totalIdx * p) / 12) * 12;
    geo.setDrawRange(0, count);
    edgeGeo.setDrawRange(0, count);
    if (strokeRef.current) strokeRef.current.visible = count > 0;
    if (edgeRef.current) edgeRef.current.visible = count > 0;

    STROKE_CURVE.getPoint(p, tip);
    const brush = brushRef.current;
    if (brush) {
      STROKE_CURVE.getTangent(p, tangent);
      brush.position.set(tip.x, tip.y + 0.04, tip.z + 0.16);
      // Lean the handle back from the direction of travel, like a held brush
      quat.setFromUnitVectors(up, tangent.clone().negate().add(new THREE.Vector3(0.3, 1.1, 0.7)).normalize());
      brush.quaternion.slerp(quat, 0.25);
    }
  });

  return (
    <group>
      {/* darker underside, very slightly behind → paint edge/shadow */}
      <mesh ref={edgeRef} geometry={edgeGeo} position={[0, 0, -0.04]} scale={[1.12, 1.0, 1]}>
        <meshStandardMaterial color={STROKE_EDGE} roughness={0.55} side={THREE.DoubleSide} />
      </mesh>
      {/* glossy wet body */}
      <mesh ref={strokeRef} geometry={geo}>
        <meshPhysicalMaterial
          color={STROKE_COLOR}
          roughness={0.3}
          clearcoat={1}
          clearcoatRoughness={0.2}
          sheen={0.5}
          sheenColor={"#ffd9b0"}
          side={THREE.DoubleSide}
        />
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
  // Start already painted to INTRO_TARGET so the stroke is visible on the very
  // first frame; scroll only extends it toward 1 from there.
  const progress = useRef(reduced ? 1 : INTRO_TARGET);
  const group = useRef<THREE.Group>(null);

  useFrame((state, dt) => {
    if (!reduced) {
      // Extend the stroke from its painted-in start toward full as you scroll
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
