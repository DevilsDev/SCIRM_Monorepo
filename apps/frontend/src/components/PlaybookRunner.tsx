import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckIcon, PlayIcon, ClockIcon } from '@heroicons/react/24/outline';

interface PlaybookStep {
  id: string;
  title: string;
  description: string;
  assignee?: string;
  dueHours?: number;
}

interface Playbook {
  id: string;
  name: string;
  description: string;
  severity: string;
  steps: PlaybookStep[];
}

const PLAYBOOKS: Playbook[] = [
  {
    id: 'supplier-disruption',
    name: 'Supplier Disruption Response',
    description: 'Standard response when a key supplier experiences a disruption event',
    severity: 'high',
    steps: [
      { id: 's1', title: 'Assess Impact', description: 'Determine which products and downstream customers are affected. Quantify financial exposure.', assignee: 'Risk Analyst', dueHours: 2 },
      { id: 's2', title: 'Notify Stakeholders', description: 'Alert procurement, operations, and executive leadership about the disruption.', assignee: 'Risk Manager', dueHours: 4 },
      { id: 's3', title: 'Activate Alternative Suppliers', description: 'Engage pre-qualified backup suppliers. Request expedited quotes and lead times.', assignee: 'Procurement', dueHours: 8 },
      { id: 's4', title: 'Adjust Inventory Plan', description: 'Review safety stock levels. Implement allocation rules if supply is constrained.', assignee: 'Supply Planning', dueHours: 12 },
      { id: 's5', title: 'Monitor Recovery', description: 'Track supplier recovery progress. Update risk score and timeline estimates daily.', assignee: 'Risk Analyst', dueHours: 24 },
      { id: 's6', title: 'Post-Incident Review', description: 'Document lessons learned. Update playbook and supplier risk profiles.', assignee: 'Risk Manager', dueHours: 72 },
    ],
  },
  {
    id: 'cyber-incident',
    name: 'Cybersecurity Incident',
    description: 'Response protocol for cyber attacks affecting supply chain systems',
    severity: 'critical',
    steps: [
      { id: 'c1', title: 'Contain Threat', description: 'Isolate affected systems. Block suspicious network traffic. Preserve forensic evidence.', assignee: 'IT Security', dueHours: 1 },
      { id: 'c2', title: 'Assess Data Exposure', description: 'Determine if supplier data, contracts, or trade secrets were compromised.', assignee: 'IT Security', dueHours: 4 },
      { id: 'c3', title: 'Notify Affected Parties', description: 'Inform affected suppliers and partners. Report to regulators if required.', assignee: 'Legal', dueHours: 24 },
      { id: 'c4', title: 'Remediate Vulnerabilities', description: 'Patch exploited systems. Update access controls and authentication.', assignee: 'IT Security', dueHours: 48 },
      { id: 'c5', title: 'Restore Operations', description: 'Verify system integrity. Restore from clean backups. Resume normal operations.', assignee: 'IT Operations', dueHours: 72 },
    ],
  },
  {
    id: 'regulatory-change',
    name: 'Regulatory Change Impact',
    description: 'Process for evaluating and responding to new regulatory requirements',
    severity: 'medium',
    steps: [
      { id: 'r1', title: 'Analyze Requirements', description: 'Review the new regulation. Identify which suppliers, products, and processes are affected.', assignee: 'Compliance', dueHours: 24 },
      { id: 'r2', title: 'Gap Assessment', description: 'Compare current compliance status against new requirements. Identify gaps.', assignee: 'Compliance', dueHours: 72 },
      { id: 'r3', title: 'Supplier Communication', description: 'Notify affected suppliers of new requirements. Request compliance evidence.', assignee: 'Procurement', dueHours: 120 },
      { id: 'r4', title: 'Implementation Plan', description: 'Create timeline and budget for achieving compliance. Assign owners.', assignee: 'Risk Manager', dueHours: 168 },
    ],
  },
  {
    id: 'natural-disaster',
    name: 'Natural Disaster Response',
    description: 'Emergency response for natural disasters affecting supply chain facilities',
    severity: 'critical',
    steps: [
      { id: 'n1', title: 'Safety Check', description: 'Verify personnel safety at affected facilities. Activate emergency contacts.', assignee: 'Operations', dueHours: 1 },
      { id: 'n2', title: 'Damage Assessment', description: 'Evaluate physical damage to facilities, inventory, and equipment.', assignee: 'Operations', dueHours: 12 },
      { id: 'n3', title: 'Supply Rerouting', description: 'Identify alternative shipping routes. Redirect inventory from unaffected warehouses.', assignee: 'Logistics', dueHours: 24 },
      { id: 'n4', title: 'Insurance & Claims', description: 'Document all damage. File insurance claims. Track recovery costs.', assignee: 'Finance', dueHours: 48 },
      { id: 'n5', title: 'Recovery Plan', description: 'Develop facility repair timeline. Establish temporary operations if needed.', assignee: 'Operations', dueHours: 72 },
    ],
  },
];

interface PlaybookRunnerProps {
  riskId?: string;
  onClose?: () => void;
}

export default function PlaybookRunner({ riskId, onClose }: PlaybookRunnerProps) {
  const { t } = useTranslation();
  const storageKey = riskId ? `scirm_playbook_${riskId}` : 'scirm_playbook_temp';

  const [selectedPlaybook, setSelectedPlaybook] = useState<Playbook | null>(null);
  const [completedSteps, setCompletedSteps] = useState<string[]>(() => {
    return JSON.parse(localStorage.getItem(storageKey) || '[]');
  });

  const toggleStep = (stepId: string) => {
    const updated = completedSteps.includes(stepId)
      ? completedSteps.filter((s) => s !== stepId)
      : [...completedSteps, stepId];
    setCompletedSteps(updated);
    localStorage.setItem(storageKey, JSON.stringify(updated));
  };

  const progress = selectedPlaybook
    ? Math.round((completedSteps.filter((s) => selectedPlaybook.steps.some((ps) => ps.id === s)).length / selectedPlaybook.steps.length) * 100)
    : 0;

  // Playbook selection
  if (!selectedPlaybook) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-gray-500 dark:text-gray-400">{t('playbooks.selectDesc', 'Choose a response playbook to guide your incident resolution')}</p>
        <div className="grid grid-cols-1 gap-3">
          {PLAYBOOKS.map((pb) => (
            <button
              key={pb.id}
              onClick={() => setSelectedPlaybook(pb)}
              className="text-left p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700 hover:shadow-sm transition-all"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{pb.name}</h3>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
                  pb.severity === 'critical' ? 'bg-red-100 text-red-800' : pb.severity === 'high' ? 'bg-orange-100 text-orange-800' : 'bg-yellow-100 text-yellow-800'
                }`}>
                  {pb.severity}
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{pb.description}</p>
              <p className="text-xs text-gray-400 mt-2">{pb.steps.length} {t('playbooks.steps', 'steps')}</p>
            </button>
          ))}
        </div>
      </div>
    );
  }

  // Playbook execution
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button
          onClick={() => setSelectedPlaybook(null)}
          className="text-xs text-blue-600 hover:text-blue-800"
        >
          &larr; {t('playbooks.backToList', 'Back to playbooks')}
        </button>
        <span className="text-xs font-medium text-gray-500">{progress}% {t('playbooks.complete', 'complete')}</span>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{selectedPlaybook.name}</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{selectedPlaybook.description}</p>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div className="bg-blue-600 rounded-full h-2 transition-all duration-300" style={{ width: `${progress}%` }} />
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {selectedPlaybook.steps.map((step, idx) => {
          const done = completedSteps.includes(step.id);
          return (
            <div
              key={step.id}
              onClick={() => toggleStep(step.id)}
              className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-all ${
                done
                  ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                  : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:border-blue-300'
              }`}
            >
              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
                done ? 'bg-green-500' : 'bg-gray-200 dark:bg-gray-700'
              }`}>
                {done ? (
                  <CheckIcon className="h-3.5 w-3.5 text-white" />
                ) : (
                  <span className="text-[10px] font-bold text-gray-500">{idx + 1}</span>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <h4 className={`text-sm font-medium ${done ? 'text-green-700 dark:text-green-300 line-through' : 'text-gray-900 dark:text-white'}`}>
                    {step.title}
                  </h4>
                  {step.dueHours && (
                    <span className="flex items-center gap-1 text-[10px] text-gray-400">
                      <ClockIcon className="h-3 w-3" />
                      {step.dueHours}h
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{step.description}</p>
                {step.assignee && (
                  <span className="inline-block mt-1 px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-[10px] rounded-full">
                    {step.assignee}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {progress === 100 && (
        <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800 text-center">
          <CheckIcon className="h-8 w-8 text-green-500 mx-auto mb-2" />
          <p className="text-sm font-medium text-green-700 dark:text-green-300">{t('playbooks.allComplete', 'All steps completed!')}</p>
          <p className="text-xs text-green-600 dark:text-green-400 mt-1">{t('playbooks.reviewNote', 'Remember to document lessons learned and update risk profiles.')}</p>
        </div>
      )}
    </div>
  );
}
