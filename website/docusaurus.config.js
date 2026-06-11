// @ts-check
const config = {
  title: 'PyDMP',
  tagline: 'Python library for controlling DMP alarm systems',
  url: 'https://amattas.github.io',
  baseUrl: '/pydmp/',
  organizationName: 'amattas',
  projectName: 'pydmp',
  onBrokenLinks: 'throw',
  themeConfig: {
    colorMode: { defaultMode: 'light', respectPrefersColorScheme: true },
    navbar: {
      title: 'PyDMP',
      items: [
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
        docs: { routeBasePath: '/', sidebarPath: './sidebars.js' },
        blog: false,
        sitemap: { lastmod: 'date', changefreq: 'weekly', priority: 0.5, filename: 'sitemap.xml' },
      },
    ],
  ],
};
module.exports = config;
