// frontend/src/pages/CabinetPage.tsx
import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "../hooks/useAuth";
import { useTelegram } from "../hooks/useTelegram";
import { useAppConfig } from "../hooks/useAppConfig";
import { apiRequest } from "../api/client";
import { RosterList, Participant } from "../components/RosterList";
import { FriendsModal } from "../components/FriendsModal";
import { PaymentBox } from "../components/PaymentBox";
import { AdminControls } from "../components/AdminControls";
import { CheckCircle2, Clock, UserPlus, XCircle, Shield, AlertCircle, LogIn, RefreshCw, MapPin, ExternalLink } from "lucide-react";

interface CabinetPageProps {
  initialGameId?: string | null;
}

export function CabinetPage({ initialGameId }: CabinetPageProps) {
  const { user, loading: authLoading, isAdmin, loginWithWidget } = useAuth();
  const { hapticImpact, hapticNotification } = useTelegram();
  const { bot_username } = useAppConfig();

  const [games, setGames] = useState<any[]>([]);
  const [selectedGameId, setSelectedGameId] = useState<string | null>(initialGameId || null);
  const [game, setGame] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [showFriendsModal, setShowFriendsModal] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Load games list
  const loadGames = useCallback(async () => {
    try {
      const data = await apiRequest<any[]>("/api/games");
      setGames(data);
      if (data.length > 0 && !selectedGameId) {
        setSelectedGameId(data[0].id);
      }
    } catch (e) {
      console.error(e);
    }
  }, [selectedGameId]);

  // Load game detail
  const loadGameDetail = useCallback(async (id: string) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const detail = await apiRequest<any>(`/api/games/${id}`);
      setGame(detail);
    } catch (e: any) {
      setErrorMsg(e.message || "Ошибка загрузки матча");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGames();
  }, [loadGames]);

  useEffect(() => {
    if (selectedGameId) {
      loadGameDetail(selectedGameId);
    }
  }, [selectedGameId, loadGameDetail]);

  // Telegram Login Widget setup for desktop browser
  const widgetRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user && widgetRef.current) {
      (window as any).onTelegramAuth = (telegramUser: any) => {
        loginWithWidget(telegramUser);
      };

      // Check if script already appended
      if (!document.getElementById("telegram-login-script")) {
        const script = document.createElement("script");
        script.id = "telegram-login-script";
        script.src = "https://telegram.org/js/telegram-widget.js?22";
        script.async = true;
        script.setAttribute("data-telegram-login", bot_username);
        script.setAttribute("data-size", "large");
        script.setAttribute("data-radius", "12");
        script.setAttribute("data-onauth", "onTelegramAuth(user)");
        script.setAttribute("data-request-access", "write");
        widgetRef.current.appendChild(script);
      }
    }
  }, [user, loginWithWidget, bot_username]);

  if (authLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
        <p className="text-xs text-slate-400">Авторизация через Telegram...</p>
      </div>
    );
  }

  // Guest / Unauthenticated screen
  if (!user) {
    return (
      <div className="max-w-md mx-auto px-4 py-12">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 text-center shadow-2xl">
          <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center text-2xl mx-auto mb-4 border border-emerald-500/20">
            🔐
          </div>
          <h2 className="text-lg font-bold text-white mb-2">Вход в Личный Кабинет</h2>
          <p className="text-xs text-slate-400 mb-6 leading-relaxed">
            Для записи на матчи, добавления друзей и отметки оплат авторизуйтесь через ваш Telegram-аккаунт.
          </p>

          <div className="space-y-4">
            <div className="flex justify-center py-2" ref={widgetRef} />

            <div className="relative flex py-2 items-center">
              <div className="flex-grow border-t border-slate-800"></div>
              <span className="flex-shrink mx-4 text-slate-500 text-[11px] uppercase">или</span>
              <div className="flex-grow border-t border-slate-800"></div>
            </div>

            <a
              href={`https://t.me/${bot_username}`}
              target="_blank"
              rel="noreferrer"
              className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 hover:brightness-110 active:scale-95 transition"
            >
              <LogIn className="w-4 h-4" />
              Открыть в Telegram (@{bot_username})
            </a>

            <p className="text-[11px] text-slate-500 pt-2">
              Внутри Telegram Mini App вход происходит мгновенно без подтверждений.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Find current user's participant entry
  const myParticipant: Participant | undefined = game?.participants?.find(
    (p: Participant) => p.telegram_id === user.telegram_id && p.type === "player"
  );

  // Find user's friends
  const myFriends: Participant[] = (game?.participants || []).filter(
    (p: Participant) => p.type === "friend" && p.added_by_telegram_id === user.telegram_id
  );

  // Handlers
  const handleJoin = async () => {
    if (!game) return;
    setActionLoading(true);
    setErrorMsg(null);
    hapticImpact("medium");
    try {
      await apiRequest(`/api/games/${game.id}/join`, { method: "POST" });
      hapticNotification("success");
      await loadGameDetail(game.id);
    } catch (err: any) {
      setErrorMsg(err.message || "Ошибка записи");
      hapticNotification("error");
    } finally {
      setActionLoading(false);
    }
  };

  const handleLeave = async () => {
    if (!game) return;
    setActionLoading(true);
    setErrorMsg(null);
    hapticImpact("medium");
    try {
      await apiRequest(`/api/games/${game.id}/leave`, { method: "POST" });
      hapticNotification("success");
      await loadGameDetail(game.id);
    } catch (err: any) {
      setErrorMsg(err.message || "Ошибка отмены записи");
      hapticNotification("error");
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddFriend = async (friendName: string) => {
    if (!game) return;
    hapticImpact("light");
    await apiRequest(`/api/games/${game.id}/friends`, {
      method: "POST",
      body: JSON.stringify({ friend_name: friendName }),
    });
    hapticNotification("success");
    await loadGameDetail(game.id);
  };

  const handleRemoveFriend = async (participantId: string) => {
    if (!game) return;
    hapticImpact("light");
    await apiRequest(`/api/games/${game.id}/friends/${participantId}`, {
      method: "DELETE",
    });
    hapticNotification("success");
    await loadGameDetail(game.id);
  };

  const handlePaymentStatus = async (status: "paid" | "not_played") => {
    if (!game) return;
    await apiRequest(`/api/games/${game.id}/payment/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
    await loadGameDetail(game.id);
  };

  const handleFriendPaymentStatus = async (participantId: string, status: "paid" | "not_played") => {
    if (!game) return;
    hapticImpact("light");
    await apiRequest(`/api/games/${game.id}/payment/status`, {
      method: "POST",
      body: JSON.stringify({ participant_id: participantId, status }),
    });
    hapticNotification("success");
    await loadGameDetail(game.id);
  };

  const handleAdminParticipantAction = async (p: Participant, action: string) => {
    if (!game || !isAdmin) return;
    const newStatus = action === "toggle_reserve" ? "reserve" : "confirmed";
    await apiRequest(`/api/admin/games/${game.id}/participants/${p.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: newStatus }),
    });
    await loadGameDetail(game.id);
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            Привет, {user.first_name}!
          </h2>
          <p className="text-xs text-slate-400">
            {isAdmin ? "Режим администратора" : "Личный кабинет игрока"}
          </p>
        </div>

        {game && (
          <button
            onClick={() => loadGameDetail(game.id)}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-800 text-slate-400 hover:text-white transition active:rotate-180"
            title="Обновить данные"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        )}
      </div>

      {errorMsg && (
        <div className="p-3 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Admin Panel (if admin) */}
      {isAdmin && game && (
        <AdminControls
          gameId={game.id}
          gameStatus={game.status}
          friendsAllowed={game.friends_allowed}
          initialCardNumber={game.payment_details?.card_number}
          initialRecipient={game.payment_details?.recipient}
          onRefresh={() => loadGameDetail(game.id)}
        />
      )}

      {/* Main Game Detail Card */}
      {loading && !game ? (
        <div className="flex items-center justify-center p-12 text-slate-400 text-xs gap-2">
          <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          Загрузка матча...
        </div>
      ) : !game ? (
        <div className="p-8 rounded-3xl bg-slate-900 border border-slate-800 text-center">
          <p className="text-xs text-slate-400">Нет доступных игр.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* My Status Card */}
          <div className="rounded-3xl p-6 bg-slate-900 border border-slate-800 shadow-xl">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
              <div>
                <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-bold uppercase tracking-wider border border-emerald-500/20 mb-2 inline-block">
                  {game.status_label}
                </span>
                <h3 className="text-xl font-extrabold text-white">{game.title}</h3>
                <p className="text-xs text-emerald-400 font-medium mt-0.5">{game.format_description}</p>
                {game.location && (game.location.title || game.location.address) && (
                  <div className="flex items-center gap-1.5 text-xs text-slate-300 mt-2">
                    <MapPin className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    <span>
                      <strong className="text-white">{game.location.title || "Стадион"}</strong>
                      {game.location.address ? ` (${game.location.address})` : ""}
                    </span>
                    {game.location.latitude && game.location.longitude && (
                      <a
                        href={`https://maps.google.com/?q=${game.location.latitude},${game.location.longitude}`}
                        target="_blank"
                        rel="noreferrer"
                        className="ml-1.5 inline-flex items-center gap-1 text-[11px] text-emerald-400 hover:text-emerald-300 underline"
                      >
                        На карте
                        <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    )}
                  </div>
                )}
              </div>

              {/* Status Badge */}
              <div className="flex items-center gap-2">
                {myParticipant?.status === "confirmed" ? (
                  <div className="px-3.5 py-2 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4" />
                    Вы в основе (№ {myParticipant.position})
                  </div>
                ) : myParticipant?.status === "reserve" ? (
                  <div className="px-3.5 py-2 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-bold flex items-center gap-1.5">
                    <Clock className="w-4 h-4" />
                    Вы в резерве (№ {myParticipant.position})
                  </div>
                ) : (
                  <div className="px-3.5 py-2 rounded-2xl bg-slate-800 text-slate-400 text-xs font-medium">
                    Вы ещё не записаны
                  </div>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            {game.status === "game_started" ? (
              <div className="pt-4 border-t border-slate-800 text-center py-2.5 bg-teal-500/10 rounded-2xl border border-teal-500/20">
                <p className="text-xs font-bold text-teal-300 flex items-center justify-center gap-2">
                  <span>⚽</span> Матч начался! Запись и отмены заблокированы.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-4 border-t border-slate-800">
                {myParticipant?.status === "confirmed" || myParticipant?.status === "reserve" ? (
                  <button
                    onClick={handleLeave}
                    disabled={actionLoading}
                    className="w-full py-3 rounded-2xl bg-slate-800 hover:bg-red-500/10 hover:border-red-500/30 hover:text-red-400 text-slate-300 border border-slate-700 font-bold text-xs transition flex items-center justify-center gap-2"
                  >
                    <XCircle className="w-4 h-4" />
                    {actionLoading ? "Отменяем..." : "Отказаться от участия"}
                  </button>
                ) : (
                  <button
                    onClick={handleJoin}
                    disabled={actionLoading || game.status === "cancelled"}
                    className="w-full py-3 rounded-2xl bg-emerald-500 hover:bg-emerald-400 text-white font-extrabold text-xs shadow-lg shadow-emerald-500/20 active:scale-95 transition flex items-center justify-center gap-2"
                  >
                    ⚽ {actionLoading ? "Записываем..." : "Буду играть (Записаться)"}
                  </button>
                )}

                {/* Friends Button (when allowed) */}
                {game.friends_allowed && (
                  <button
                    onClick={() => setShowFriendsModal(true)}
                    className="w-full py-3 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold text-xs transition flex items-center justify-center gap-2"
                  >
                    <UserPlus className="w-4 h-4 text-emerald-400" />
                    Добавить друга {myFriends.length > 0 && `(${myFriends.length}/3)`}
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Payment Box (if open) */}
          {game.status === "payment_collection" && (
            <PaymentBox
              pricePerPlayer={game.price}
              totalCost={game.total_cost}
              cardNumber={game.payment_details?.card_number}
              recipient={game.payment_details?.recipient}
              myStatus={myParticipant?.payment_status || "pending"}
              onStatusChange={handlePaymentStatus}
              myFriends={myFriends.filter((f) => f.status === "confirmed")}
              onFriendStatusChange={handleFriendPaymentStatus}
            />
          )}

          {/* Roster Breakdown */}
          <div className="rounded-3xl p-6 bg-slate-900 border border-slate-800 shadow-xl">
            <h4 className="text-base font-bold text-white mb-4">Текущий состав матча</h4>
            <RosterList
              participants={game.participants || []}
              maxPlayers={game.max_players}
              showPayments={game.status === "payment_collection"}
              isAdmin={isAdmin}
              onParticipantAction={handleAdminParticipantAction}
            />
          </div>
        </div>
      )}

      {/* Friends Modal */}
      <FriendsModal
        isOpen={showFriendsModal}
        onClose={() => setShowFriendsModal(false)}
        myFriends={myFriends}
        onAddFriend={handleAddFriend}
        onRemoveFriend={handleRemoveFriend}
      />
    </div>
  );
}
