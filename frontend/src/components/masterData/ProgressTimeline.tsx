import { Check, Circle } from 'lucide-react';
import { BLUE, TEAL, BORDER, GREEN, TEXT_SECONDARY } from '../../constants/theme';

export type TimelineStep = {
  id: string;
  label: string;
  detail?: string;
  done: boolean;
  active?: boolean;
};

type Props = {
  steps: TimelineStep[];
};

export function ProgressTimeline({ steps }: Props) {
  return (
    <div
      style={{
        background: 'white',
        border: `1px solid ${BORDER}`,
        borderRadius: 12,
        padding: '18px 22px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
        marginBottom: 20,
      }}
    >
      <div
        style={{
          fontSize: '0.6875rem',
          fontWeight: 600,
          color: TEXT_SECONDARY,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          marginBottom: 14,
        }}
      >
        Setup Progress
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 0,
          flexWrap: 'wrap',
        }}
      >
        {steps.map((step, i) => {
          const isLast = i === steps.length - 1;
          return (
            <div
              key={step.id}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                flex: isLast ? '0 1 auto' : '1 1 0',
                minWidth: 140,
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: step.done
                        ? GREEN
                        : step.active
                          ? BLUE
                          : '#F3F4F6',
                      border: step.done || step.active ? 'none' : `1.5px solid ${BORDER}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    {step.done ? (
                      <Check size={14} color="white" strokeWidth={3} />
                    ) : (
                      <Circle
                        size={10}
                        color={step.active ? 'white' : '#9CA3AF'}
                        fill={step.active ? 'white' : 'transparent'}
                      />
                    )}
                  </div>
                  {!isLast && (
                    <div
                      style={{
                        flex: 1,
                        height: 2,
                        marginLeft: 8,
                        marginRight: 8,
                        background: step.done ? TEAL : '#E5E7EB',
                        minWidth: 24,
                      }}
                    />
                  )}
                </div>
                <div>
                  <div
                    style={{
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: step.done || step.active ? '#111827' : '#6B7280',
                    }}
                  >
                    {step.label}
                  </div>
                  {step.detail && (
                    <div style={{ fontSize: '0.75rem', color: TEXT_SECONDARY, marginTop: 2 }}>
                      {step.detail}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
