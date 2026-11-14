import { SECTIONS } from "@/lib/constants";

interface Props {
  activeId: string;
  onSelect: (id: string) => void;
  mobileMenuOpen: boolean;
  onCloseMobileMenu: () => void;
}

export function Sidebar({
  activeId,
  onSelect,
  mobileMenuOpen,
  onCloseMobileMenu,
}: Props) {
  const handleClick = (id: string) => {
    onSelect(id);
    onCloseMobileMenu();
  };

  return (
    <>
      {/* Mobile Backdrop */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-20 md:hidden"
          onClick={onCloseMobileMenu}
          aria-hidden="true"
        />
      )}

      {/* Sidebar navigation */}
      <aside
        className={`fixed top-12 bottom-0 left-0 z-20 w-52 bg-surface border-r border-border flex flex-col transition-transform duration-200 ease-out md:translate-x-0 ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
        aria-label="Section navigation"
      >
        <div className="p-3 border-b border-border">
          <span className="text-11 uppercase font-semibold tracking-wider text-muted px-2">
            Navigation
          </span>
        </div>

        <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {SECTIONS.map((sec) => {
            const isActive = activeId === sec.id;
            return (
              <button
                key={sec.id}
                type="button"
                onClick={() => handleClick(sec.id)}
                className={`w-full text-left px-2.5 py-1.5 text-13 rounded-control transition-colors duration-150 flex items-center justify-between group ${
                  isActive
                    ? "bg-surface-2 text-text font-medium"
                    : "text-muted hover:text-text hover:bg-surface-2/60 font-normal"
                }`}
              >
                <span className="truncate">{sec.label}</span>
                {isActive && (
                  <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0 ml-2" />
                )}
              </button>
            );
          })}
        </nav>

        <div className="p-3 border-t border-border text-11 text-muted">
          <div className="px-2">Autonomous Operations</div>
        </div>
      </aside>
    </>
  );
}

