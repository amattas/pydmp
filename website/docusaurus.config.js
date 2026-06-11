// @ts-check
const config = {
  title: 'PyDMP',
  tagline: 'Python library for controlling DMP alarm systems',
  url: 'https://amattas.github.io',
  baseUrl: '/pydmp/',
  organizationName: 'amattas',
  projectName: 'pydmp',
  onBrokenLinks: 'throw',
  favicon: 'img/favicon.svg',
  themeConfig: {
    colorMode: { defaultMode: 'light', respectPrefersColorScheme: true },
    navbar: {
      title: 'PyDMP',
      logo: { src: 'img/logo.svg', width: 26, height: 26 },
      items: [
        { to: '/guide/getting-started', label: 'Guide', position: 'left' },
        { to: '/api/reference', label: 'API', position: 'left' },
        { to: '/compatibility', label: 'Compatibility', position: 'left' },
        { type: 'docsVersionDropdown', position: 'right' },
        {
          href: 'https://github.com/amattas/pydmp',
          label: 'GitHub',
          position: 'right',
        },
        {
          href: 'https://pypi.org/project/pydmp/',
          label: 'PyPI',
          position: 'right',
        },
      ],
    },
  },
  presets: [
    [
      '@docusaurus/preset-classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.js',
          // Latest cut release serves at the site root; main's docs live at
          // /dev. Cutting a version is part of the release-bump PR:
          //   (generate website/docs/api/reference.md)
          //   npm run docusaurus docs:version X.Y.Z
          versions: {
            current: { label: 'dev (main)', path: 'dev' },
          },
        },
        blog: false,
        theme: { customCss: './src/css/custom.css' },
        sitemap: { lastmod: 'date', changefreq: 'weekly', priority: 0.5, filename: 'sitemap.xml' },
      },
    ],
  ],
  themes: [
    [
      // Self-hosted full-text search — no external service, indexed at build time.
      require.resolve('@easyops-cn/docusaurus-search-local'),
      {
        hashed: true,
        docsRouteBasePath: '/',
        indexBlog: false,
        highlightSearchTermsOnTargetPage: true,
      },
    ],
  ],
};
module.exports = config;
