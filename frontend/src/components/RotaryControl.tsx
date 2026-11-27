import React, { useRef } from 'react';

interface RotaryControlProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  defaultValue?: number;
  unit?: string;
  accent?: string;
  onChange: (val: number) => void;
}

export const RotaryControl: React.FC<RotaryControlProps> = ({
  label,
  value,
  min,
  max,
  defaultValue = 0,
  unit = '',
  accent = '#38BDF8',
  onChange,
}) => {
  const dragStartRef = useRef<{ y: number; val: number } | null>(null);

  const norm = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const angleDeg = -135 + norm * 270;

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    dragStartRef.current = { y: e.clientY, val: value };

    const handleMove = (ev: MouseEvent) => {
      if (!dragStartRef.current) return;
      const dy = dragStartRef.current.y - ev.clientY;
      const range = max - min;
      const next = Math.max(min, Math.min(max, dragStartRef.current.val + (dy / 120) * range));
      onChange(Number(next.toFixed(2)));
    };

    const handleUp = () => {
      dragStartRef.current = null;
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
  };

  return (
    <div className="flex flex-col items-center gap-1 select-none">
      <div
        onMouseDown={onMouseDown}
        onDoubleClick={() => onChange(defaultValue)}
        title="Arraste verticalmente para ajustar • Duplo clique para resetar"
        className="relative w-10 h-10 rounded-full bg-[#0B0D12] border border-[#242C3D] flex items-center justify-center cursor-ns-resize shadow-inner hover:border-slate-500 transition-colors"
      >
        {/* Dial Arc Indicator */}
        <div
          className="w-7 h-7 rounded-full bg-[#161B26] border border-[#2D3748] relative"
          style={{ transform: `rotate(${angleDeg}deg)` }}
        >
          <span
            className="absolute left-1/2 top-0.5 -translate-x-1/2 w-1 h-2.5 rounded-full"
            style={{ backgroundColor: accent }}
          />
        </div>
      </div>
      <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">{label}</span>
      <span className="text-[10px] font-mono-tech text-slate-300">
        {value > 0 && unit === 'dB' ? `+${value.toFixed(1)}` : value.toFixed(1)}
        {unit}
      </span>
    </div>
  );
};
