import { useState } from "react";
import { CheckCircle2, KeyRound, UserRound } from "lucide-react";
import Panel from "../components/Panel";
import { PageHeading } from "../components/Feedback";

const PROFILE_KEY = "hireflow.localProfile";

function readProfile() {
  try {
    const value = window.localStorage.getItem(PROFILE_KEY);
    return value
      ? JSON.parse(value)
      : { fullName: "HR workspace", email: "" };
  } catch {
    return { fullName: "HR workspace", email: "" };
  }
}

export default function SettingsPage() {
  const [profile, setProfile] = useState(readProfile);
  const [saved, setSaved] = useState(false);

  function saveProfile(event) {
    event.preventDefault();
    window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2500);
  }

  return (
    <>
      <PageHeading
        eyebrow="Workspace"
        title="Settings"
        description="Manage local display preferences and review integration setup guidance."
      />
      <div className="settings-grid">
        <Panel
          title="HR profile"
          subtitle="The backend currently does not expose an authenticated account settings API."
        >
          <form className="settings-form" onSubmit={saveProfile}>
            <label>
              Display name
              <input
                maxLength={120}
                value={profile.fullName}
                onChange={(event) =>
                  setProfile({ ...profile, fullName: event.target.value })
                }
              />
            </label>
            <label>
              Email address
              <input
                type="email"
                value={profile.email}
                onChange={(event) =>
                  setProfile({ ...profile, email: event.target.value })
                }
              />
            </label>
            <p className="form-note">
              This display profile is saved in this browser only. It is not an
              authenticated backend user account.
            </p>
            <button className="button button-primary" type="submit">
              {saved ? <CheckCircle2 size={16} /> : <UserRound size={16} />}
              {saved ? "Saved locally" : "Save display preferences"}
            </button>
          </form>
        </Panel>

        <Panel
          title="Integrations"
          subtitle="Integration secrets are kept on the FastAPI server."
        >
          <div className="settings-integration">
            <span className="integration-icon"><KeyRound size={18} /></span>
            <div>
              <strong>Google Calendar</strong>
              <p>
                Configure service-account access and the calendar time zone in
                the backend environment.
              </p>
            </div>
            <span className="status-badge status-unknown">Status not exposed</span>
          </div>
          <div className="settings-integration">
            <span className="integration-icon integration-violet"><KeyRound size={18} /></span>
            <div>
              <strong>Resend email</strong>
              <p>Set a Resend API key and verified sender on the backend.</p>
            </div>
            <span className="status-badge status-unknown">Status not exposed</span>
          </div>
          <div className="settings-integration">
            <span className="integration-icon integration-green"><KeyRound size={18} /></span>
            <div>
              <strong>Vapi screening</strong>
              <p>Vapi calls are initiated manually and require HR consent confirmation.</p>
            </div>
            <span className="status-badge status-unknown">Status not exposed</span>
          </div>
          <p className="form-note settings-note">
            The API does not expose integration health or credential status, so
            this dashboard does not infer whether a provider is connected.
            Never enter API keys in the browser.
          </p>
        </Panel>
      </div>
    </>
  );
}
