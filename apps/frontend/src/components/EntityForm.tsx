import { TrashIcon } from '@heroicons/react/24/outline';

export interface EntityData {
  id: string;
  name: string;
  type: string;
  location: string;
}

interface EntityFormProps {
  entity: EntityData;
  onChange: (entity: EntityData) => void;
  onRemove: () => void;
  canRemove: boolean;
}

export default function EntityForm({ entity, onChange, onRemove, canRemove }: EntityFormProps) {
  const update = (field: keyof EntityData, value: string) => {
    onChange({ ...entity, [field]: value });
  };

  return (
    <div className="flex items-start gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900">
      <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <input
          type="text"
          placeholder="Entity name"
          value={entity.name}
          onChange={(e) => update('name', e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
        />
        <select
          value={entity.type}
          onChange={(e) => update('type', e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
        >
          <option value="">Select type</option>
          <option value="supplier">Supplier</option>
          <option value="facility">Facility</option>
          <option value="route">Route</option>
          <option value="product">Product</option>
        </select>
        <input
          type="text"
          placeholder="Location (optional)"
          value={entity.location}
          onChange={(e) => update('location', e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
        />
      </div>
      {canRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="p-2 text-gray-400 hover:text-red-500 transition-colors"
        >
          <TrashIcon className="h-5 w-5" />
        </button>
      )}
    </div>
  );
}
