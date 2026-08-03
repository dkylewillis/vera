/**
 * Wait for the sidecar request itself to settle, then end its active UI state
 * before callers perform slower follow-up work such as refreshing a library.
 */
export async function awaitConversionRequest<T>(
  request: Promise<T>,
  onSettled: () => void,
): Promise<T> {
  try {
    return await request;
  } finally {
    onSettled();
  }
}
