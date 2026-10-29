import type { Metadata } from "next";
import { IBM_Plex_Mono, Newsreader, Outfit } from "next/font/google";

import "./globals.css";

const sans = Outfit({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-sans" });
const serif = Newsreader({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-serif", adjustFontFallback: false });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "SWARM EVOLVE-X",
  description: "Engineering lab for the gripper surrogate, swarm replay, archived failures, and the toy energy balance.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${serif.variable} ${mono.variable} font-sans antialiased`}>{children}</body>
    </html>
  );
}
