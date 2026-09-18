import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fleetpilot/ui/tokens.css";
import "./globals.css";
export const metadata: Metadata = {
  title: { default: "FleetPilot", template: "%s | FleetPilot" },
  description: "Run the fleet. Not the chaos.",
  manifest: "/manifest.webmanifest",
};
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#08111F",
};
export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  await connection();
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
