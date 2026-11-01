// frontend/src/components/PaymentBox.tsx
import React, { useState } from "react";
import { CreditCard, Copy, Check, CheckCircle2, XCircle } from "lucide-react";
import { useTelegram } from "../hooks/useTelegram";

interface PaymentBoxProps {
  pricePerPlayer: number;
  totalCost?: number | null;
  cardNumber?: string;
  recipient?: string;
  myStatus: "paid" | "not_played" | "unpaid" | "pending";
  onStatusChange: (status: "paid" | "not_played") => Promise<void>;
}

export function PaymentBox({
  pricePerPlayer,
  totalCost,
  cardNumber,
  recipient,
  myStatus,
  onStatusChange,
}: PaymentBoxProps) {
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const { hapticNotification } = useTelegram();

  const handleCopy = () => {
    if (!cardNumber) return;
    navigator.clipboard.writeText(cardNumber.replace(/\s+/g, ""));
    setCopied(true);
    hapticNotification("success");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleAction = async (status: "paid" | "not_played") => {
    setLoading(true);
    try {
      await onStatusChange(status);
      hapticNotification("success");
    } catch (e) {
      hapticNotification("error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-3xl p-5 border border-emerald-500/30 shadow-xl relative overflow-hidden">
      <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
            <CreditCard className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white">Оплата за аренду</h4>
            <p className="text-[11px] text-slate-400">
              {totalCost ? `Общая аренда поля: ${totalCost} грн` : "Сбор открыт"}
            </p>
          </div>
        </div>
        <div className="text-right">
          <span className="text-xl font-extrabold text-emerald-400">{pricePerPlayer} ₴</span>
          <span className="text-[10px] text-slate-400 block">с человека</span>
        </div>
      </div>

      {/* Card Info */}
      {cardNumber && (
        <div className="bg-slate-950/60 rounded-2xl p-3 border border-slate-800 mb-4 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">
              Банковская карта
            </p>
            <p className="text-sm font-mono font-bold text-slate-200 tracking-wider">{cardNumber}</p>
            {recipient && <p className="text-[11px] text-slate-400 mt-0.5">{recipient}</p>}
          </div>
          <button
            onClick={handleCopy}
            className="p-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition flex items-center gap-1.5 text-xs font-medium"
          >
            {copied ? (
              <>
                <Check className="w-4 h-4 text-emerald-400" />
                <span className="text-emerald-400">Скопировано</span>
              </>
            ) : (
              <>
                <Copy className="w-4 h-4" />
                <span>Копия</span>
              </>
            )}
          </button>
        </div>
      )}

      {/* Action Buttons */}
      <div className="grid grid-cols-2 gap-2.5">
        <button
          onClick={() => handleAction("paid")}
          disabled={loading || myStatus === "paid"}
          className={`py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-1.5 ${
            myStatus === "paid"
              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 cursor-default"
              : "bg-emerald-500 hover:bg-emerald-400 text-white shadow-lg shadow-emerald-500/20 active:scale-95"
          }`}
        >
          <CheckCircle2 className="w-4 h-4" />
          {myStatus === "paid" ? "Вы оплатили ✅" : "Я оплатил"}
        </button>

        <button
          onClick={() => handleAction("not_played")}
          disabled={loading || myStatus === "not_played"}
          className={`py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-1.5 ${
            myStatus === "not_played"
              ? "bg-slate-800 text-slate-400 border border-slate-700 cursor-default"
              : "bg-slate-800 hover:bg-slate-700 text-slate-300 active:scale-95"
          }`}
        >
          <XCircle className="w-4 h-4" />
          {myStatus === "not_played" ? "Не играл" : "Не играл"}
        </button>
      </div>
    </div>
  );
}
