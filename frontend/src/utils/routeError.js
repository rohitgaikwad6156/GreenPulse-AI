/** A stale deployment chunk may need fresh HTML before React can import it. */
export function isChunkLoadError(error) {
  const message = error instanceof Error ? error.message : "";
  return /Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk [\w-]+ failed|ChunkLoadError/i
    .test(`${error?.name || ""} ${message}`);
}
