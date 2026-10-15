export const formatUserDisplay = (userOrItem, currentAuthUser = null) => {
  if (!userOrItem) return { name: '', identifier: '', initial: 'U', avatar: '', isMe: false };

  const email = userOrItem.owner_email || userOrItem.grantee_email || userOrItem.email || '';
  const name = (userOrItem.owner_name || userOrItem.grantee_name || userOrItem.name || '').trim();
  const avatar = userOrItem.owner_avatar || userOrItem.grantee_avatar || userOrItem.avatar_url || '';
  const telegramId = userOrItem.owner_telegram_id || userOrItem.grantee_telegram_id || userOrItem.telegram_id;

  const isMe = !!(currentAuthUser && (
    (email && currentAuthUser.email && email.toLowerCase() === currentAuthUser.email.toLowerCase()) ||
    (telegramId && currentAuthUser.telegram_id && String(telegramId) === String(currentAuthUser.telegram_id))
  ));

  let identifier = email;
  if (email.endsWith('@telegram.user')) {
    if (telegramId) {
      identifier = `Telegram ID: ${telegramId}`;
    } else {
      const match = email.match(/^tg_(\d+)@/);
      identifier = match ? `Telegram ID: ${match[1]}` : 'Telegram User';
    }
  }

  const displayName = name || identifier || email || 'User';
  const initial = (displayName[0] || 'U').toUpperCase();

  return {
    isMe,
    name: displayName,
    identifier,
    initial,
    avatar,
  };
};
