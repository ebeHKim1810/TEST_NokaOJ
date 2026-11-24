import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Clock } from 'lucide-react';

interface Props {
  startTime: string;
  serverTime?: string;
  isRegistered: boolean;
  isStaff: boolean;
  isLoggedIn: boolean;
  onRegister: () => void;
  onStarted: () => void;
}

const pad2 = (n: number) => String(Math.max(0, Math.floor(n))).padStart(2, '0');

export const ContestCountdown: React.FC<Props> = ({
  startTime,
  serverTime,
  isRegistered,
  isStaff,
  isLoggedIn,
  onRegister,
  onStarted,
}) => {
  const offsetRef = useRef(0);
  const triggeredRef = useRef(false);

  const computeRemainingSec = () => {
    const startMs = new Date(startTime).getTime();
    const nowMs = Date.now() + offsetRef.current;
    return Math.max(0, Math.ceil((startMs - nowMs) / 1000));
  };

  const [remaining, setRemaining] = useState<number>(() => {
    offsetRef.current = serverTime ? new Date(serverTime).getTime() - Date.now() : 0;
    return computeRemainingSec();
  });

  useEffect(() => {
    offsetRef.current = serverTime ? new Date(serverTime).getTime() - Date.now() : 0;
    triggeredRef.current = false;
    setRemaining(computeRemainingSec());

    const timer = window.setInterval(() => {
      const next = computeRemainingSec();
      setRemaining(next);
      if (next <= 0 && !triggeredRef.current) {
        triggeredRef.current = true;
        window.clearInterval(timer);
        onStarted();
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [startTime, serverTime]);

  const days = Math.floor(remaining / 86400);
  const hours = Math.floor((remaining % 86400) / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;

  return (
    <div className="noka-section p-6 text-center space-y-4 bg-[#2A5C99]/[0.03] dark:bg-[#89B4E8]/[0.05] border-[#2A5C99]/20 dark:border-[#89B4E8]/20">
      <div className="inline-flex items-center gap-2 rounded-full bg-[#2A5C99]/10 dark:bg-[#89B4E8]/15 px-3 py-1 text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8]">
        {isRegistered && !isStaff ? (
          <>
            <CheckCircle2 className="h-3.5 w-3.5" /> Bạn đã tham gia kỳ thi — Đếm ngược tới giờ bắt đầu
          </>
        ) : (
          <>
            <Clock className="h-3.5 w-3.5" /> Kỳ thi chưa bắt đầu — Đếm ngược tới giờ thi
          </>
        )}
      </div>

      <div className="flex items-center justify-center gap-2 sm:gap-3 font-mono">
        {days > 0 && (
          <div className="min-w-[4.25rem] rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-[#14171D] px-3 py-2.5">
            <div className="text-2xl sm:text-3xl font-bold text-zinc-900 dark:text-zinc-100 tabular-nums">
              {pad2(days)}
            </div>
            <div className="text-[11px] text-zinc-500 mt-0.5">Ngày</div>
          </div>
        )}
        <div className="min-w-[4.25rem] rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-[#14171D] px-3 py-2.5">
          <div className="text-2xl sm:text-3xl font-bold text-zinc-900 dark:text-zinc-100 tabular-nums">
            {pad2(hours)}
          </div>
          <div className="text-[11px] text-zinc-500 mt-0.5">Giờ</div>
        </div>
        <span className="text-2xl font-bold text-zinc-400">:</span>
        <div className="min-w-[4.25rem] rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-[#14171D] px-3 py-2.5">
          <div className="text-2xl sm:text-3xl font-bold text-zinc-900 dark:text-zinc-100 tabular-nums">
            {pad2(minutes)}
          </div>
          <div className="text-[11px] text-zinc-500 mt-0.5">Phút</div>
        </div>
        <span className="text-2xl font-bold text-zinc-400">:</span>
        <div className="min-w-[4.25rem] rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-[#14171D] px-3 py-2.5">
          <div className="text-2xl sm:text-3xl font-bold text-[#2A5C99] dark:text-[#89B4E8] tabular-nums">
            {pad2(seconds)}
          </div>
          <div className="text-[11px] text-zinc-500 mt-0.5">Giây</div>
        </div>
      </div>

      <p className="text-xs text-zinc-500">
        Bắt đầu lúc: <span className="font-mono font-medium text-zinc-700 dark:text-zinc-300">{new Date(startTime).toLocaleString()}</span>
        {isRegistered && ' · Trang sẽ tự động mở danh sách bài khi đến giờ thi.'}
      </p>

      {!isStaff && !isRegistered && (
        <div>
          {isLoggedIn ? (
            <button type="button" onClick={onRegister} className="noka-btn-primary">
              Tham gia kỳ thi
            </button>
          ) : (
            <Link to="/login" className="noka-btn-primary">
              Đăng nhập để tham gia
            </Link>
          )}
        </div>
      )}
    </div>
  );
};
