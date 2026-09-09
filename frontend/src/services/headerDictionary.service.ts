import { apiRequest } from '../api';

export type HeaderDictionary = {
  customer: string[];
  product: string[];
  quantity: string[];
};

export type HeaderDictionaryUpdateResult = {
  dictionary: HeaderDictionary;
  changes: {
    added: Record<string, string[]>;
    removed: Record<string, string[]>;
  };
};

export const HeaderDictionaryService = {
  get: async (): Promise<HeaderDictionary> => {
    const res = await apiRequest<{ success: boolean; data: HeaderDictionary }>(
      '/admin/header-dictionary'
    );
    return res.data;
  },

  save: async (payload: HeaderDictionary): Promise<HeaderDictionaryUpdateResult> => {
    const res = await apiRequest<{ success: boolean; data: HeaderDictionaryUpdateResult }>(
      '/admin/header-dictionary',
      { method: 'PUT', body: payload }
    );
    return res.data;
  },
};
