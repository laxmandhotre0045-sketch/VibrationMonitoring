/**
 * echarts-gl ships no TypeScript definitions. Importing it for side effects registers
 * grid3D / line3D / scatter3D on the global echarts instance.
 */
declare module "echarts-gl";
