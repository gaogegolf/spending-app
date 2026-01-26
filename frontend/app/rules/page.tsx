'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getRules, createRule, updateRule, deleteRule, toggleRule, getRuleMatchCount, applyRuleToTransactions, refreshRuleMatchCounts } from '@/lib/api';
import { Rule, RuleAction, RuleType, RuleListResponse } from '@/lib/types';
import { TRANSACTION_TYPES, getCategoriesForType } from '@/lib/categories';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const RULE_TYPES: { value: RuleType; label: string; description: string }[] = [
  { value: 'MERCHANT_MATCH', label: 'Merchant Match', description: 'Match by merchant name (case-insensitive contains)' },
  { value: 'DESCRIPTION_REGEX', label: 'Description Regex', description: 'Match by regular expression pattern' },
  { value: 'AMOUNT_RANGE', label: 'Amount Range', description: 'Match transactions within a dollar range' },
  { value: 'CATEGORY_OVERRIDE', label: 'Category Override', description: 'Override category for specific pattern' },
];

interface FormData {
  name: string;
  rule_type: RuleType;
  pattern: string;
  action: RuleAction;
  priority: number;
  description: string;
  is_active: boolean;
  // For amount range
  amount_min?: string;
  amount_max?: string;
}

const defaultFormData: FormData = {
  name: '',
  rule_type: 'MERCHANT_MATCH',
  pattern: '',
  action: {
    transaction_type: 'EXPENSE',
    category: '',
  },
  priority: 100,
  description: '',
  is_active: true,
};

export default function RulesPage() {
  const router = useRouter();
  const [rules, setRules] = useState<Rule[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState<FormData>(defaultFormData);
  const [formError, setFormError] = useState<string | null>(null);

  // Delete state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Rule | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Toggling state
  const [togglingId, setTogglingId] = useState<string | null>(null);

  // Apply to existing transactions state
  const [showApplyPrompt, setShowApplyPrompt] = useState(false);
  const [applyRuleId, setApplyRuleId] = useState<string | null>(null);
  const [applyMatchCount, setApplyMatchCount] = useState(0);
  const [applying, setApplying] = useState(false);
  const [applySuccess, setApplySuccess] = useState<string | null>(null);

  // Refresh match counts state
  const [refreshingCounts, setRefreshingCounts] = useState(false);

  useEffect(() => {
    loadRules();
  }, [searchQuery, typeFilter, statusFilter]);

  useEffect(() => {
    if (showModal || showDeleteConfirm || showApplyPrompt) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [showModal, showDeleteConfirm, showApplyPrompt]);

  async function loadRules() {
    try {
      setLoading(true);
      setError(null);

      const data: RuleListResponse = await getRules({
        search: searchQuery || undefined,
        rule_type: typeFilter || undefined,
        is_active: statusFilter === 'all' ? undefined : statusFilter === 'active',
      });

      setRules(data.rules || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load rules');
    } finally {
      setLoading(false);
    }
  }

  function openCreateModal() {
    setEditingRule(null);
    setFormData(defaultFormData);
    setFormError(null);
    setShowModal(true);
  }

  function openEditModal(rule: Rule) {
    setEditingRule(rule);

    // Parse amount range pattern if applicable
    let amountMin = '';
    let amountMax = '';
    if (rule.rule_type === 'AMOUNT_RANGE') {
      try {
        const parsed = JSON.parse(rule.pattern);
        amountMin = parsed.min?.toString() || '';
        amountMax = parsed.max?.toString() || '';
      } catch {
        // ignore parse error
      }
    }

    setFormData({
      name: rule.name,
      rule_type: rule.rule_type,
      pattern: rule.pattern,
      action: rule.action,
      priority: rule.priority,
      description: rule.description || '',
      is_active: rule.is_active,
      amount_min: amountMin,
      amount_max: amountMax,
    });
    setFormError(null);
    setShowModal(true);
  }

  function closeModal() {
    setShowModal(false);
    setEditingRule(null);
    setFormData(defaultFormData);
    setFormError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    // Validation
    if (!formData.name.trim()) {
      setFormError('Rule name is required');
      return;
    }

    if (!formData.action.category) {
      setFormError('Category is required');
      return;
    }

    // Build pattern based on rule type
    let pattern = formData.pattern;
    if (formData.rule_type === 'AMOUNT_RANGE') {
      const min = formData.amount_min ? parseFloat(formData.amount_min) : undefined;
      const max = formData.amount_max ? parseFloat(formData.amount_max) : undefined;
      if (min === undefined && max === undefined) {
        setFormError('At least one of min or max amount is required');
        return;
      }
      pattern = JSON.stringify({ min, max });
    } else if (!pattern.trim()) {
      setFormError('Pattern is required');
      return;
    }

    try {
      setSaving(true);

      const ruleData = {
        name: formData.name.trim(),
        rule_type: formData.rule_type,
        pattern,
        action: formData.action,
        priority: formData.priority,
        description: formData.description.trim() || undefined,
        is_active: formData.is_active,
      };

      if (editingRule) {
        await updateRule(editingRule.id, ruleData);
        closeModal();
        await loadRules();

        // Check if there are existing transactions that match this updated rule
        try {
          const matchResult = await getRuleMatchCount(editingRule.id);
          if (matchResult.match_count > 0) {
            setApplyRuleId(editingRule.id);
            setApplyMatchCount(matchResult.match_count);
            setShowApplyPrompt(true);
          }
        } catch {
          // Silently ignore if match count fails - rule was still updated
        }
      } else {
        // Create new rule
        const newRule = await createRule(ruleData);
        closeModal();
        await loadRules();

        // Check if there are existing transactions that match this rule
        try {
          const matchResult = await getRuleMatchCount(newRule.id);
          if (matchResult.match_count > 0) {
            setApplyRuleId(newRule.id);
            setApplyMatchCount(matchResult.match_count);
            setShowApplyPrompt(true);
          }
        } catch {
          // Silently ignore if match count fails - rule was still created
        }
      }
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to save rule');
    } finally {
      setSaving(false);
    }
  }

  async function handleApplyRule() {
    if (!applyRuleId) return;

    try {
      setApplying(true);
      const result = await applyRuleToTransactions(applyRuleId);
      setApplySuccess(`Successfully applied rule to ${result.updated_count} transactions!`);
      setShowApplyPrompt(false);
      setApplyRuleId(null);
      await loadRules(); // Refresh to update match_count
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to apply rule');
      setShowApplyPrompt(false);
    } finally {
      setApplying(false);
    }
  }

  function closeApplyPrompt() {
    setShowApplyPrompt(false);
    setApplyRuleId(null);
    setApplyMatchCount(0);
  }

  async function handleRefreshCounts() {
    try {
      setRefreshingCounts(true);
      setError(null);
      const result = await refreshRuleMatchCounts();
      await loadRules();
      if (result.updated_rules > 0) {
        setApplySuccess(`Updated match counts for ${result.updated_rules} rules`);
      } else {
        setApplySuccess('All match counts are up to date');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh match counts');
    } finally {
      setRefreshingCounts(false);
    }
  }

  async function handleToggle(rule: Rule) {
    try {
      setTogglingId(rule.id);
      await toggleRule(rule.id);
      setRules(rules.map(r =>
        r.id === rule.id ? { ...r, is_active: !r.is_active } : r
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle rule');
    } finally {
      setTogglingId(null);
    }
  }

  function handleDeleteClick(rule: Rule) {
    setDeleteTarget(rule);
    setShowDeleteConfirm(true);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;

    try {
      setDeleting(true);
      await deleteRule(deleteTarget.id);
      setShowDeleteConfirm(false);
      setDeleteTarget(null);
      await loadRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete rule');
    } finally {
      setDeleting(false);
    }
  }

  function getRuleTypeColor(type: RuleType): string {
    switch (type) {
      case 'MERCHANT_MATCH':
        return 'bg-indigo-100 text-indigo-800';
      case 'DESCRIPTION_REGEX':
        return 'bg-yellow-100 text-yellow-800';
      case 'AMOUNT_RANGE':
        return 'bg-cyan-100 text-cyan-800';
      case 'CATEGORY_OVERRIDE':
        return 'bg-pink-100 text-pink-800';
      case 'COMPOSITE':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  }

  function formatActionSummary(action: RuleAction): string {
    const parts: string[] = [];
    if (action.category) parts.push(`Category: ${action.category}`);
    if (action.transaction_type) parts.push(`Type: ${action.transaction_type}`);
    return parts.join(', ') || 'No action defined';
  }

  function formatPattern(rule: Rule): string {
    if (rule.rule_type === 'AMOUNT_RANGE') {
      try {
        const parsed = JSON.parse(rule.pattern);
        const parts: string[] = [];
        if (parsed.min !== undefined) parts.push(`min: $${parsed.min}`);
        if (parsed.max !== undefined) parts.push(`max: $${parsed.max}`);
        return parts.join(', ');
      } catch {
        return rule.pattern;
      }
    }
    return rule.pattern;
  }

  // Filter panel state
  const [filtersExpanded, setFiltersExpanded] = useState(true);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Page Header */}
        <div className="flex items-start justify-between mb-10">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg">
              <span className="text-2xl">⚙️</span>
            </div>
            <div>
              <h1 className="text-4xl font-black bg-gradient-to-r from-gray-900 via-indigo-900 to-purple-900 bg-clip-text text-transparent">
                Classification Rules
              </h1>
              <p className="text-gray-600 mt-1">
                Create custom rules to automatically categorize transactions
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleRefreshCounts}
              disabled={refreshingCounts}
              className="px-4 py-2.5 bg-white/80 backdrop-blur-sm border border-gray-200 text-gray-700 rounded-xl hover:bg-white hover:border-indigo-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium text-sm flex items-center gap-2 shadow-sm"
              title="Recalculate match counts based on current transactions"
            >
              {refreshingCounts ? (
                <>
                  <span className="animate-spin">⟳</span>
                  Refreshing...
                </>
              ) : (
                <>
                  <span>🔄</span>
                  Refresh Counts
                </>
              )}
            </button>
            <button
              onClick={openCreateModal}
              className="px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-xl hover:from-indigo-700 hover:to-purple-700 transition-all font-semibold text-sm flex items-center gap-2 shadow-lg"
            >
              <span>+</span>
              Create Rule
            </button>
          </div>
        </div>

      {/* Filters */}
      <div className="bg-white/70 backdrop-blur-xl shadow-xl rounded-2xl border border-white/50 overflow-hidden mb-6">
        {/* Filter Header */}
        <div
          className="px-6 py-4 bg-gradient-to-r from-gray-50/80 to-white/80 border-b border-gray-100 cursor-pointer hover:bg-gray-50/90 transition-colors"
          onClick={() => setFiltersExpanded(!filtersExpanded)}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center bg-indigo-100 transition-transform duration-200 ${filtersExpanded ? 'rotate-90' : ''}`}>
                <span className="text-indigo-600 text-sm font-bold">▶</span>
              </div>
              <h2 className="text-lg font-semibold text-gray-900">Filters</h2>
              {(searchQuery || typeFilter || statusFilter !== 'all') && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                  Active
                </span>
              )}
            </div>
          </div>
        </div>

        {filtersExpanded && (
          <div className="p-6">
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
              {/* Search */}
              <div>
                <label htmlFor="search" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Search by Name
                </label>
                <div className="relative">
                  <input
                    type="text"
                    id="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Type to search..."
                    className="w-full pl-9 pr-3 py-2.5 border border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm bg-gray-50 hover:bg-white transition-colors"
                  />
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">🔍</span>
                </div>
              </div>

              {/* Rule Type Filter */}
              <div>
                <label htmlFor="type-filter" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Rule Type
                </label>
                <select
                  id="type-filter"
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="w-full px-3 py-2.5 border border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm bg-gray-50 hover:bg-white transition-colors"
                >
                  <option value="">All Types</option>
                  {RULE_TYPES.map((rt) => (
                    <option key={rt.value} value={rt.value}>
                      {rt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Status Filter */}
              <div>
                <label htmlFor="status-filter" className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Status
                </label>
                <select
                  id="status-filter"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as 'all' | 'active' | 'inactive')}
                  className="w-full px-3 py-2.5 border border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm bg-gray-50 hover:bg-white transition-colors"
                >
                  <option value="all">All</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Rules Table */}
      {loading ? (
        <div className="bg-white/70 backdrop-blur-xl shadow-xl rounded-2xl border border-white/50 p-12">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-indigo-200 border-t-indigo-600 mx-auto mb-4"></div>
            <p className="text-gray-500">Loading rules...</p>
          </div>
        </div>
      ) : rules.length === 0 ? (
        <div className="bg-white/70 backdrop-blur-xl shadow-xl rounded-2xl border border-white/50 p-12">
          <div className="text-center">
            <div className="text-6xl mb-4">⚙️</div>
            <h3 className="text-xl font-semibold text-gray-900 mb-2">No rules found</h3>
            <p className="text-gray-500 mb-6">Create custom rules to automatically categorize your transactions</p>
            <button
              onClick={openCreateModal}
              className="px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-xl hover:from-indigo-700 hover:to-purple-700 transition-all font-semibold shadow-lg"
            >
              Create your first rule
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-white/70 backdrop-blur-xl shadow-xl rounded-2xl border border-white/50 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Rule Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Pattern
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Action
                </th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Priority
                </th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Matches
                </th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Active
                </th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {rules.map((rule) => (
                <tr key={rule.id} className={`hover:bg-gray-50 ${!rule.is_active ? 'opacity-60' : ''}`}>
                  <td className="px-6 py-4 text-sm">
                    <button
                      onClick={() => router.push(`/transactions?match_rule_pattern=${rule.id}`)}
                      className="font-medium text-gray-900 hover:text-indigo-600 hover:underline text-left"
                      title="View transactions matching this rule"
                    >
                      {rule.name}
                    </button>
                    {rule.description && (
                      <div className="text-gray-500 text-xs mt-1 max-w-xs truncate" title={rule.description}>
                        {rule.description}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getRuleTypeColor(rule.rule_type)}`}>
                      {RULE_TYPES.find(rt => rt.value === rule.rule_type)?.label || rule.rule_type}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    <div className="max-w-xs truncate" title={formatPattern(rule)}>
                      {formatPattern(rule)}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    <div className="max-w-xs truncate" title={formatActionSummary(rule.action)}>
                      {formatActionSummary(rule.action)}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-center">
                    {rule.priority}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-center">
                    {rule.match_count}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-center">
                    <button
                      onClick={() => handleToggle(rule)}
                      disabled={togglingId === rule.id}
                      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${
                        rule.is_active ? 'bg-indigo-600' : 'bg-gray-200'
                      } ${togglingId === rule.id ? 'opacity-50' : ''}`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                          rule.is_active ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-center">
                    <div className="flex items-center justify-center gap-3">
                      <button
                        onClick={() => openEditModal(rule)}
                        className="text-sm text-gray-400 hover:text-indigo-600"
                        title="Edit rule"
                      >
                        📝
                      </button>
                      <button
                        onClick={() => handleDeleteClick(rule)}
                        className="text-sm text-gray-400 hover:text-red-600"
                        title="Delete rule"
                      >
                        🗑️
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Stats */}
      {!loading && rules.length > 0 && (
        <div className="mt-4 text-sm text-gray-500">
          Showing {rules.length} of {total} rules
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !saving) {
              closeModal();
            }
          }}
        >
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">
                {editingRule ? 'Edit Rule' : 'Create Rule'}
              </h3>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-6">
              {formError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="text-red-800 text-sm">{formError}</p>
                </div>
              )}

              {/* Rule Name */}
              <div>
                <label htmlFor="rule-name" className="block text-sm font-medium text-gray-700 mb-1">
                  Rule Name *
                </label>
                <input
                  type="text"
                  id="rule-name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., Amazon Purchases"
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                />
              </div>

              {/* Rule Type */}
              <div>
                <label htmlFor="rule-type" className="block text-sm font-medium text-gray-700 mb-1">
                  Rule Type *
                </label>
                <select
                  id="rule-type"
                  value={formData.rule_type}
                  onChange={(e) => setFormData({
                    ...formData,
                    rule_type: e.target.value as RuleType,
                    pattern: '',
                    amount_min: '',
                    amount_max: '',
                  })}
                  disabled={!!editingRule}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm disabled:bg-gray-100"
                >
                  {RULE_TYPES.map((rt) => (
                    <option key={rt.value} value={rt.value}>
                      {rt.label}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-gray-500">
                  {RULE_TYPES.find(rt => rt.value === formData.rule_type)?.description}
                </p>
              </div>

              {/* Pattern (dynamic based on rule type) */}
              {formData.rule_type === 'AMOUNT_RANGE' ? (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="amount-min" className="block text-sm font-medium text-gray-700 mb-1">
                      Min Amount ($)
                    </label>
                    <input
                      type="number"
                      id="amount-min"
                      value={formData.amount_min || ''}
                      onChange={(e) => setFormData({ ...formData, amount_min: e.target.value })}
                      placeholder="0.00"
                      step="0.01"
                      min="0"
                      className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    />
                  </div>
                  <div>
                    <label htmlFor="amount-max" className="block text-sm font-medium text-gray-700 mb-1">
                      Max Amount ($)
                    </label>
                    <input
                      type="number"
                      id="amount-max"
                      value={formData.amount_max || ''}
                      onChange={(e) => setFormData({ ...formData, amount_max: e.target.value })}
                      placeholder="100.00"
                      step="0.01"
                      min="0"
                      className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    />
                  </div>
                </div>
              ) : (
                <div>
                  <label htmlFor="pattern" className="block text-sm font-medium text-gray-700 mb-1">
                    Pattern *
                  </label>
                  <input
                    type="text"
                    id="pattern"
                    value={formData.pattern}
                    onChange={(e) => setFormData({ ...formData, pattern: e.target.value })}
                    placeholder={
                      formData.rule_type === 'MERCHANT_MATCH'
                        ? 'e.g., AMAZON, WHOLE FOODS'
                        : formData.rule_type === 'DESCRIPTION_REGEX'
                        ? 'e.g., UBER.*TRIP|LYFT.*'
                        : 'Enter pattern...'
                    }
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                  />
                  {formData.rule_type === 'DESCRIPTION_REGEX' && (
                    <p className="mt-1 text-xs text-gray-500">
                      Use regular expression syntax. Pattern is case-insensitive.
                    </p>
                  )}
                </div>
              )}

              {/* Action Section */}
              <div className="border-t border-gray-200 pt-6">
                <h4 className="text-sm font-medium text-gray-900 mb-4">Action (when rule matches)</h4>

                <div className="grid grid-cols-2 gap-4">
                  {/* Transaction Type - moved first so category can depend on it */}
                  <div>
                    <label htmlFor="action-type" className="block text-sm font-medium text-gray-700 mb-1">
                      Transaction Type *
                    </label>
                    <select
                      id="action-type"
                      value={formData.action.transaction_type || 'EXPENSE'}
                      onChange={(e) => setFormData({
                        ...formData,
                        action: { ...formData.action, transaction_type: e.target.value, category: '' }
                      })}
                      className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    >
                      {TRANSACTION_TYPES.map((type) => (
                        <option key={type} value={type}>
                          {type.charAt(0) + type.slice(1).toLowerCase()}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Category - filtered by transaction type */}
                  <div>
                    <label htmlFor="action-category" className="block text-sm font-medium text-gray-700 mb-1">
                      Category *
                    </label>
                    <select
                      id="action-category"
                      value={formData.action.category || ''}
                      onChange={(e) => setFormData({
                        ...formData,
                        action: { ...formData.action, category: e.target.value }
                      })}
                      className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    >
                      <option value="">Select category...</option>
                      {getCategoriesForType(formData.action.transaction_type || 'EXPENSE').map((cat) => (
                        <option key={cat.id} value={cat.name}>
                          {cat.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

              </div>

              {/* Priority */}
              <div>
                <label htmlFor="priority" className="block text-sm font-medium text-gray-700 mb-1">
                  Priority (lower = higher priority)
                </label>
                <input
                  type="number"
                  id="priority"
                  value={formData.priority}
                  onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) || 100 })}
                  min="0"
                  className="block w-32 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                />
              </div>

              {/* Description */}
              <div>
                <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
                  Description (optional)
                </label>
                <textarea
                  id="description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={2}
                  placeholder="Add a note about this rule..."
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                />
              </div>

              {/* Active Checkbox */}
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is-active"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                />
                <label htmlFor="is-active" className="ml-2 text-sm text-gray-700">
                  Rule is active
                </label>
              </div>

              {/* Buttons */}
              <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
                <button
                  type="button"
                  onClick={closeModal}
                  disabled={saving}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                >
                  {saving ? 'Saving...' : editingRule ? 'Update Rule' : 'Create Rule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Success Message */}
      {applySuccess && (
        <div className="fixed bottom-4 right-4 bg-green-50 border border-green-200 rounded-lg p-4 shadow-lg z-40 max-w-md">
          <div className="flex items-center justify-between">
            <p className="text-green-800">{applySuccess}</p>
            <button
              onClick={() => setApplySuccess(null)}
              className="ml-4 text-green-600 hover:text-green-800"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* Apply to Existing Transactions Prompt */}
      {showApplyPrompt && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !applying) {
              closeApplyPrompt();
            }
          }}
        >
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Apply Rule to Existing Transactions?</h3>
            <p className="text-gray-600 mb-4">
              This rule matches <strong>{applyMatchCount}</strong> existing transaction{applyMatchCount !== 1 ? 's' : ''}.
              Would you like to apply the rule to these transactions now?
            </p>
            <p className="text-gray-500 text-sm mb-6">
              You can also apply rules later from the rule's menu.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={closeApplyPrompt}
                disabled={applying}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Skip
              </button>
              <button
                onClick={handleApplyRule}
                disabled={applying}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
              >
                {applying ? 'Applying...' : `Apply to ${applyMatchCount} Transaction${applyMatchCount !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && deleteTarget && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !deleting) {
              setShowDeleteConfirm(false);
              setDeleteTarget(null);
            }
          }}
        >
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Confirm Delete</h3>
            <p className="text-gray-600 mb-2">
              Are you sure you want to delete the rule <strong>"{deleteTarget.name}"</strong>?
            </p>
            {deleteTarget.match_count > 0 && (
              <p className="text-amber-600 text-sm mb-4">
                This rule has matched {deleteTarget.match_count} transaction{deleteTarget.match_count !== 1 ? 's' : ''}.
              </p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeleteTarget(null);
                }}
                disabled={deleting}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
