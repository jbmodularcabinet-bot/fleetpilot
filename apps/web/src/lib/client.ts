import { cachedRead, rawOwner, establish } from "./offline";
export async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  if (
    method === "GET" &&
    typeof window !== "undefined" &&
    window.location.pathname.startsWith("/driver") &&
    (path === "/driver/maintenance-vehicles" ||
      /^\/driver\/trips/.test(path) ||
      /^\/trips\/[a-f0-9-]+\/(delivery-attempts|expenses)/.test(path))
  ) {
    if (!(await rawOwner())) {
      const identityResponse = await fetch("/api/v1/me", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!identityResponse.ok)
        throw new Error("Sign in to prepare offline access.");
      await establish(await identityResponse.json());
    }
    return cachedRead<T>(path);
  }
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  if (response.status === 401) {
    window.location.assign("/login?expired=1");
    throw new Error("Your session expired. Please sign in.");
  }
  const data = response.status === 204 ? undefined : await response.json();
  if (!response.ok)
    throw new Error(
      data?.error?.message ?? "Unable to save. Please try again.",
    );
  return data as T;
}
