"use client";

import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Float } from "@react-three/drei";
import * as THREE from "three";

import type { FlowStage } from "@/components/hero-flow/flow-stage-data";

const STAGE_POSITIONS: [number, number, number][] = [
  [-6.4, 0, 0],
  [-2.15, 0.35, 0],
  [2.15, -0.25, 0],
  [6.4, 0, 0],
];

interface FlowNodeProps {
  position: [number, number, number];
  color: string;
  intensity: number;
}

function FlowNode({ position, color, intensity }: FlowNodeProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const radius = 0.5 + intensity * 0.45;

  useFrame((_state, delta) => {
    if (!meshRef.current) {
      return;
    }
    meshRef.current.rotation.y += delta * 0.25;
    meshRef.current.rotation.x += delta * 0.08;
  });

  return (
    <group position={position}>
      <Float speed={1.4} rotationIntensity={0.25} floatIntensity={0.7}>
        <mesh ref={meshRef}>
          <icosahedronGeometry args={[radius, 1]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={0.55}
            roughness={0.3}
            metalness={0.35}
          />
        </mesh>
        <mesh scale={1.9}>
          <sphereGeometry args={[radius, 16, 16]} />
          <meshBasicMaterial color={color} transparent opacity={0.1} depthWrite={false} />
        </mesh>
      </Float>
    </group>
  );
}

interface FlowSegmentProps {
  start: THREE.Vector3;
  end: THREE.Vector3;
  colorFrom: string;
  colorTo: string;
  count: number;
}

function FlowSegment({ start, end, colorFrom, colorTo, count }: FlowSegmentProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  const curve = useMemo(() => {
    const mid = new THREE.Vector3().lerpVectors(start, end, 0.5);
    mid.y += 1.15;
    mid.z += 0.6;
    return new THREE.QuadraticBezierCurve3(start, mid, end);
  }, [start, end]);

  const phases = useMemo(
    () => Array.from({ length: count }, () => Math.random()),
    [count],
  );

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) {
      return;
    }
    const from = new THREE.Color(colorFrom);
    const to = new THREE.Color(colorTo);
    for (let i = 0; i < count; i += 1) {
      const blended = from.clone().lerp(to, i / Math.max(1, count - 1));
      mesh.setColorAt(i, blended);
    }
    if (mesh.instanceColor) {
      mesh.instanceColor.needsUpdate = true;
    }
  }, [count, colorFrom, colorTo]);

  useFrame((state) => {
    const mesh = meshRef.current;
    if (!mesh) {
      return;
    }
    const elapsed = state.clock.getElapsedTime();
    for (let i = 0; i < count; i += 1) {
      const t = (elapsed * 0.16 + phases[i]) % 1;
      const point = curve.getPoint(t);
      dummy.position.copy(point);
      const pulse = 0.05 + 0.025 * Math.sin(elapsed * 3 + i);
      dummy.scale.setScalar(Math.max(0.02, pulse));
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

interface RevenueFlowSceneProps {
  stages: FlowStage[];
}

/**
 * The four-stage recovery pipeline (At Risk -> AI Decision -> Recovery ->
 * Recovered) as glowing nodes connected by particle streams. Node size and
 * stream density are driven by `stages`, which is derived from the real
 * dashboard summary -- this renders the pipeline's current shape, not a
 * decorative animation.
 */
export function RevenueFlowScene({ stages }: RevenueFlowSceneProps) {
  const positions = useMemo(
    () => STAGE_POSITIONS.map((position) => new THREE.Vector3(...position)),
    [],
  );

  return (
    <>
      <ambientLight intensity={0.5} />
      <pointLight position={[-4, 4, 6]} intensity={60} color="#818cf8" distance={20} />
      <pointLight position={[4, -3, 6]} intensity={45} color="#34d399" distance={20} />
      <pointLight position={[0, 2, -4]} intensity={20} color="#f59e0b" distance={20} />

      {stages.map((stage, index) => (
        <FlowNode
          key={stage.id}
          position={STAGE_POSITIONS[index]}
          color={stage.colorHex}
          intensity={stage.intensity}
        />
      ))}

      {stages.slice(0, -1).map((stage, index) => {
        const nextStage = stages[index + 1];
        const avgIntensity = (stage.intensity + nextStage.intensity) / 2;
        return (
          <FlowSegment
            key={`${stage.id}-to-${nextStage.id}`}
            start={positions[index]}
            end={positions[index + 1]}
            colorFrom={stage.colorHex}
            colorTo={nextStage.colorHex}
            count={Math.max(6, Math.round(20 * avgIntensity))}
          />
        );
      })}
    </>
  );
}
