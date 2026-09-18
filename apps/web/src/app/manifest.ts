import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FleetPilot Driver",
    short_name: "FleetPilot",
    description: "One trip. One next action.",
    start_url: "/driver",
    scope: "/driver",
    display: "standalone",
    icons: [
      {
        src: "/driver-icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
    background_color: "#F6F8FA",
    theme_color: "#08111F",
  };
}
