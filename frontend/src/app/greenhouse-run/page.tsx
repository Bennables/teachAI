"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function GreenhouseRunPage() {
  const router = useRouter();

  useEffect(() => {
    const qs = window.location.search.replace(/^\?/, "");
    router.replace(qs ? `/greenhouse?${qs}` : "/greenhouse");
  }, [router]);

  return null;
}
