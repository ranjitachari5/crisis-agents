import { useEffect, useState } from "react";
import { SECTIONS } from "@/lib/constants";

export function useScrollSpy(offset = 80): {
  activeId: string;
  scrollTo: (id: string) => void;
} {
  const [activeId, setActiveId] = useState<string>(SECTIONS[0].id);

  useEffect(() => {
    const handleScroll = () => {
      const scrollPosition = window.scrollY + offset;

      for (let i = SECTIONS.length - 1; i >= 0; i--) {
        const section = document.getElementById(SECTIONS[i].id);
        if (section) {
          const top = section.offsetTop;
          if (scrollPosition >= top) {
            setActiveId(SECTIONS[i].id);
            return;
          }
        }
      }

      if (SECTIONS.length > 0) {
        setActiveId(SECTIONS[0].id);
      }
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();

    return () => {
      window.removeEventListener("scroll", handleScroll);
    };
  }, [offset]);

  const scrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return { activeId, scrollTo };
}
