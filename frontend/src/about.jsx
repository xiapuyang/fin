/* About page — version, license, GitHub, check-for-updates link */

const About = ({ meta }) => {
  const m = meta || {};
  const repoUrl = m.repo_url || "https://github.com/xiapuyang/fin";
  const releasesUrl = m.releases_url || `${repoUrl}/releases/latest`;
  const licenseUrl = m.license_url || `${repoUrl}/blob/main/LICENSE`;
  const license = m.license || "MIT";

  const row = { display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "12px 0", borderBottom: "1px solid var(--line)" };
  const label = { fontSize: 12, color: "var(--ink-4)", letterSpacing: ".05em", textTransform: "uppercase" };
  const value = { fontSize: 14, color: "var(--ink)", fontWeight: 500 };
  const linkStyle = { ...value, color: "var(--accent)", textDecoration: "none", cursor: "pointer" };

  return (
    <div style={{ maxWidth: 560, margin: "48px auto", padding: "0 32px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 32 }}>
        <Icon name="logo" size={56}/>
        <div>
          <div className="serif-cn" style={{ fontSize: 32, fontWeight: 700, lineHeight: 1 }}>fin</div>
          <div style={{ fontSize: 12, color: "var(--ink-4)", marginTop: 6 }}>{I18N.t("about.tagline")}</div>
        </div>
      </div>

      <div style={row}>
        <span style={label}>{I18N.t("about.version")}</span>
        <span className="mono" style={value}>v{m.version || "?"}</span>
      </div>

      <div style={row}>
        <span style={label}>{I18N.t("about.check_updates")}</span>
        <a href={releasesUrl} target="_blank" rel="noopener noreferrer" style={linkStyle}>
          {releasesUrl.replace("https://", "")}
        </a>
      </div>

      <div style={row}>
        <span style={label}>{I18N.t("about.license")}</span>
        <a href={licenseUrl} target="_blank" rel="noopener noreferrer" style={linkStyle}>
          {license}
        </a>
      </div>

      <div style={row}>
        <span style={label}>{I18N.t("about.github")}</span>
        <a href={repoUrl} target="_blank" rel="noopener noreferrer" style={linkStyle}>
          {repoUrl}
        </a>
      </div>

      <div style={{ marginTop: 32, fontSize: 11, color: "var(--ink-5)", textAlign: "center" }}>
        {I18N.t("about.copyright")}
      </div>
    </div>
  );
};
