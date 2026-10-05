import { Component, Fragment, createRef } from "react";
import { Link } from "react-router-dom";
import { TriangleAlert } from "lucide-react";
import { isChunkLoadError } from "../utils/routeError.js";

export default class RouteErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, attempt: 0 };
    this.heading = createRef();
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    if (import.meta.env.DEV) console.error("GreenPulse route render failed", error, info);
    this.heading.current?.focus({ preventScroll: true });
  }

  retry = () => {
    if (isChunkLoadError(this.state.error)) {
      window.location.reload();
      return;
    }
    this.setState(({ attempt }) => ({ hasError: false, error: null, attempt: attempt + 1 }));
  };

  render() {
    if (this.state.hasError) return (
      <section className="route-error" role="alert" aria-labelledby="route-error-heading">
        <TriangleAlert size={26} strokeWidth={1.7} aria-hidden="true" className="route-error-icon" />
        <p className="eyebrow">Page recovery</p>
        <h1 id="route-error-heading" tabIndex={-1} ref={this.heading}>
          Something went wrong on this page.
        </h1>
        <p>GreenPulse could not render this view. Your other workspace pages are still available.</p>
        <div className="route-error-actions">
          <button type="button" className="button-primary" onClick={this.retry}>Retry</button>
          <Link to="/" className="button-secondary"
            onClick={this.props.pathname === "/" ? this.retry : undefined}>
            Return to Overview
          </Link>
        </div>
        <p className="route-error-note">If the problem continues, refresh the page or choose another workspace section.</p>
      </section>
    );
    return <Fragment key={this.state.attempt}>{this.props.children}</Fragment>;
  }
}
