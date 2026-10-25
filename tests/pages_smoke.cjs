/* Compatibility entry point for the reviewed static-site browser regression.
 * The news/map suite retains provenance, source-date, CDS, empty/stale/unknown,
 * safety and desktop/mobile coverage and adds visit-state and network navigation.
 * See news_map_smoke.cjs for isolated-runtime and output-directory requirements.
 */
'use strict';
require('./news_map_smoke.cjs');
