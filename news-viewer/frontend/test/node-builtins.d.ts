declare module "node:fs" {
  export interface Dirent {
    name: string;
    isDirectory(): boolean;
  }

  export function existsSync(path: string): boolean;
  export function readdirSync(
    path: string,
    options: { withFileTypes: true },
  ): Dirent[];
  export function readFileSync(path: string, encoding: "utf8"): string;
}

declare module "node:path" {
  const pathApi: {
    dirname(p: string): string;
    join(...paths: string[]): string;
    relative(from: string, to: string): string;
    resolve(...paths: string[]): string;
  };
  export default pathApi;
}

declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}
