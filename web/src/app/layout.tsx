import type { Metadata } from "next";
import "./globals.css";
import "./premium.css";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "RevenueOps | AI 商家运营工作台",
  description: "面向跨境 DTC 商家的 AI 运营决策与实验闭环工作台。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
