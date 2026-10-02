import { Link } from 'react-router';
import { RootIQMark } from '@/components/brand/Logo';

export function ServicesPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
      <RootIQMark size={48} />
      <h1 className="text-[length:var(--fs-xl)] font-semibold text-[var(--text-1)]">Services</h1>
      <p className="max-w-md text-sm text-[var(--text-2)]">
        حالة الخدمات الحية تظهر الآن في Operations وداخل كل حادثة.
        <br />
        Live service health is shown on Operations and inside each incident.
      </p>
      <Link to="/" className="rq-btn-secondary inline-flex items-center px-4">
        فتح Operations
      </Link>
    </div>
  );
}
