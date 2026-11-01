// frontend/src/components/FriendsModal.tsx
import React, { useState } from "react";
import { X, UserPlus, Trash2 } from "lucide-react";
import { Participant } from "./RosterList";

interface FriendsModalProps {
  isOpen: boolean;
  onClose: () => void;
  myFriends: Participant[];
  onAddFriend: (name: string) => Promise<void>;
  onRemoveFriend: (participantId: string) => Promise<void>;
}

export function FriendsModal({
  isOpen,
  onClose,
  myFriends,
  onAddFriend,
  onRemoveFriend,
}: FriendsModalProps) {
  const [friendName, setFriendName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!friendName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await onAddFriend(friendName.trim());
      setFriendName("");
    } catch (err: any) {
      setError(err.message || "Не удалось добавить друга");
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (id: string) => {
    setLoading(true);
    try {
      await onRemoveFriend(id);
    } catch (err: any) {
      setError(err.message || "Не удалось удалить друга");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-1.5 rounded-full bg-slate-800 text-slate-400 hover:text-white transition"
        >
          <X className="w-4 h-4" />
        </button>

        <h3 className="text-base font-bold text-white mb-1 flex items-center gap-2">
          <UserPlus className="w-5 h-5 text-emerald-400" />
          Управление друзьями
        </h3>
        <p className="text-xs text-slate-400 mb-4">
          Вы можете записать до 3 друзей. Они займут места в общей очереди.
        </p>

        {error && (
          <div className="mb-4 p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
            {error}
          </div>
        )}

        {/* Existing friends */}
        {myFriends.length > 0 && (
          <div className="mb-5 space-y-2">
            <p className="text-xs font-semibold text-slate-300">Ваши добавленные друзья ({myFriends.length}/3):</p>
            {myFriends.map((f) => (
              <div
                key={f.id}
                className="flex items-center justify-between p-2.5 rounded-xl bg-slate-800/60 border border-slate-700/60"
              >
                <div className="truncate pr-2">
                  <span className="text-xs font-medium text-slate-200">{f.display_name}</span>
                  <span className="text-[10px] ml-2 text-slate-400 font-mono">
                    ({f.status === "confirmed" ? "в основе" : "в резерве"})
                  </span>
                </div>
                <button
                  onClick={() => handleRemove(f.id)}
                  className="p-1 text-slate-400 hover:text-red-400 transition"
                  title="Убрать друга"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Add Friend Form */}
        {myFriends.length < 3 ? (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Имя друга:</label>
              <input
                type="text"
                value={friendName}
                onChange={(e) => setFriendName(e.target.value)}
                placeholder="Например, Андрей (вратарь)"
                maxLength={40}
                required
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition"
              />
            </div>
            <button
              type="submit"
              disabled={loading || !friendName.trim()}
              className="w-full py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-semibold transition disabled:opacity-50 shadow-md shadow-emerald-500/10"
            >
              {loading ? "Добавляем..." : "+ Добавить друга"}
            </button>
          </form>
        ) : (
          <p className="text-xs text-amber-400/90 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded-xl text-center">
            Достигнут лимит (максимум 3 друга).
          </p>
        )}
      </div>
    </div>
  );
}
