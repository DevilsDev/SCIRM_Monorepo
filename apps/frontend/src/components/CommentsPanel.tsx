import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChatBubbleLeftIcon } from '@heroicons/react/24/outline';
import { TextArea } from './ui';

interface Comment {
  id: string;
  text: string;
  author: string;
  timestamp: string;
}

interface CommentsPanelProps {
  entityId: string;
  entityType: string; // 'risk' | 'supplier' | 'alert'
}

export default function CommentsPanel({ entityId, entityType }: CommentsPanelProps) {
  const { t } = useTranslation();
  const storageKey = `scirm_comments_${entityType}_${entityId}`;

  const [comments, setComments] = useState<Comment[]>(() => {
    return JSON.parse(localStorage.getItem(storageKey) || '[]');
  });
  const [newComment, setNewComment] = useState('');

  const addComment = () => {
    if (!newComment.trim()) return;
    const comment: Comment = {
      id: Date.now().toString(),
      text: newComment.trim(),
      author: 'Sarah Chen',
      timestamp: new Date().toISOString(),
    };
    const updated = [...comments, comment];
    setComments(updated);
    localStorage.setItem(storageKey, JSON.stringify(updated));
    setNewComment('');
  };

  const deleteComment = (id: string) => {
    const updated = comments.filter((c) => c.id !== id);
    setComments(updated);
    localStorage.setItem(storageKey, JSON.stringify(updated));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <ChatBubbleLeftIcon className="h-5 w-5 text-gray-400" />
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
          {t('comments.title', 'Comments')} ({comments.length})
        </h3>
      </div>

      {/* Comment list */}
      {comments.length > 0 && (
        <div className="space-y-3 max-h-60 overflow-y-auto">
          {comments.map((comment) => (
            <div key={comment.id} className="group p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{comment.author}</span>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-400">{new Date(comment.timestamp).toLocaleString()}</span>
                  <button
                    onClick={() => deleteComment(comment.id)}
                    className="opacity-0 group-hover:opacity-100 text-[10px] text-red-400 hover:text-red-600 transition-opacity"
                  >
                    {t('common.delete', 'Delete')}
                  </button>
                </div>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-300">{comment.text}</p>
            </div>
          ))}
        </div>
      )}

      {/* New comment */}
      <div className="space-y-2">
        <TextArea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder={t('comments.placeholder', 'Add a comment...')}
          rows={2}
          showCount
          maxLength={500}
        />
        <button
          onClick={addComment}
          disabled={!newComment.trim()}
          className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {t('comments.add', 'Add Comment')}
        </button>
      </div>
    </div>
  );
}
