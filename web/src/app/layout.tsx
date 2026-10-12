import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import { cookies } from "next/headers";
import "./globals.css";

const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-serif", display: "swap" });
const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Operador", template: "%s · Operador" },
  description: "Tu operador automático de inversiones en IOL.",
  robots: { index: false, follow: false },
  appleWebApp: { capable: true, title: "Operador", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3efe6" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0d0c" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const tema = (await cookies()).get("tema")?.value;
  const dataTheme = tema === "light" || tema === "dark" ? tema : undefined;
  return (
    <html lang="es-AR" data-theme={dataTheme} className={`${serif.variable} ${geist.variable} ${geistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
