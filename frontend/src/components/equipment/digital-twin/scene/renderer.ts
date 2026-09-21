/**
 * Digital Twin — renderer, environment and lighting rig.
 *
 * Studio setup: ACES filmic tone mapping over an sRGB output, a PMREM
 * environment baked from RoomEnvironment for believable metal, one
 * shadow-casting key, a cool rim to separate the machine from the backdrop, a
 * low hemisphere fill, and PCF soft shadows landing on an invisible
 * ShadowMaterial floor.
 *
 * The canvas is transparent — the backdrop is a CSS radial gradient on the
 * stage behind it, so it follows the app's light/dark theme without the
 * renderer having to know about either.
 */

import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export const TONE_MAPPING_EXPOSURE = 0.78;
export const ENV_MAP_INTENSITY = 0.6;
/** Cap: a 3x DPR phone would otherwise render nine times the pixels. */
export const MAX_PIXEL_RATIO = 2;

export interface Stage {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  /** Everything model-specific hangs here, so a swap never touches the rig. */
  content: THREE.Group;
  shadowFloor: THREE.Mesh;
  dispose: () => void;
}

export const CAMERA_FOV = 42;

/**
 * Build the renderer and the permanent parts of the scene.
 *
 * The renderer creates its **own** canvas, which the caller appends. That is
 * deliberate: teardown calls `forceContextLoss()`, and a canvas that has lost
 * its context that way can never obtain another one. Re-using a canvas element
 * owned by React would therefore work exactly once — and under StrictMode,
 * which mounts effects twice in development, that means never.
 *
 * Throws if WebGL is unavailable; the caller turns that into the fallback
 * message rather than a blank canvas.
 */
export function createStage(): Stage {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: "high-performance",
  });

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO));
  renderer.setClearAlpha(0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = TONE_MAPPING_EXPOSURE;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();

  // PMREM is generated once from RoomEnvironment. Both the source scene and
  // the generator are disposed straight away — only the render target's
  // texture is kept, and that is released in `dispose`.
  const pmrem = new THREE.PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const environment = pmrem.fromScene(room, 0.04);
  scene.environment = environment.texture;
  room.dispose();
  pmrem.dispose();

  const camera = new THREE.PerspectiveCamera(CAMERA_FOV, 1, 0.05, 500);
  camera.position.set(6, 4, 8);

  const key = new THREE.DirectionalLight(0xfff4e6, 2.1);
  key.position.set(5.5, 8, 6);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.bias = -0.0006;
  key.shadow.normalBias = 0.02;
  const shadowCamera = key.shadow.camera;
  shadowCamera.near = 0.5;
  shadowCamera.far = 60;
  shadowCamera.left = -12;
  shadowCamera.right = 12;
  shadowCamera.top = 12;
  shadowCamera.bottom = -12;
  scene.add(key, key.target);

  const rim = new THREE.DirectionalLight(0xbfd4ff, 1.15);
  rim.position.set(-7, 3.5, -6);
  scene.add(rim);

  const fill = new THREE.HemisphereLight(0xffffff, 0x8a97a8, 0.35);
  scene.add(fill);

  // Catches the shadow without painting a surface, so the CSS backdrop shows
  // through everywhere the machine is not.
  const shadowFloor = new THREE.Mesh(
    new THREE.PlaneGeometry(80, 80),
    new THREE.ShadowMaterial({ opacity: 0.22 })
  );
  shadowFloor.rotation.x = -Math.PI / 2;
  shadowFloor.receiveShadow = true;
  scene.add(shadowFloor);

  const content = new THREE.Group();
  content.name = "content";
  scene.add(content);

  return {
    renderer,
    scene,
    camera,
    content,
    shadowFloor,
    dispose: () => {
      environment.dispose();
      scene.environment = null;
      shadowFloor.geometry.dispose();
      (shadowFloor.material as THREE.Material).dispose();
      key.shadow.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}

/**
 * Apply the environment intensity to everything a model brought with it.
 *
 * GLB materials arrive with `envMapIntensity` at 1, which reads blown out
 * under this exposure. Also switches on shadow casting, which glTF does not
 * carry.
 */
export function applyStandardMaterialSettings(root: THREE.Object3D) {
  root.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) return;

    mesh.castShadow = true;
    mesh.receiveShadow = true;

    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    materials.forEach((material) => {
      const standard = material as THREE.MeshStandardMaterial;
      if (standard && "envMapIntensity" in standard) {
        standard.envMapIntensity = ENV_MAP_INTENSITY;
      }
    });
  });
}

/**
 * Sit the shadow floor just under the model and size the key light's shadow
 * frustum to it, so a long pump set gets the same shadow quality as a motor.
 */
export function fitShadowFloor(stage: Stage, box: THREE.Box3) {
  stage.shadowFloor.position.y = box.min.y - 0.02;

  const size = box.getSize(new THREE.Vector3());
  const centre = box.getCenter(new THREE.Vector3());
  const reach = Math.max(size.x, size.z) * 0.85 + 2;

  const key = stage.scene.children.find(
    (child): child is THREE.DirectionalLight =>
      (child as THREE.DirectionalLight).isDirectionalLight === true &&
      (child as THREE.DirectionalLight).castShadow
  );
  if (!key) return;

  key.target.position.copy(centre);
  key.target.updateMatrixWorld();
  key.position.set(centre.x + reach * 0.7, box.max.y + reach, centre.z + reach * 0.8);

  const shadowCamera = key.shadow.camera;
  shadowCamera.left = -reach;
  shadowCamera.right = reach;
  shadowCamera.top = reach;
  shadowCamera.bottom = -reach;
  shadowCamera.far = reach * 4 + 10;
  shadowCamera.updateProjectionMatrix();
}
