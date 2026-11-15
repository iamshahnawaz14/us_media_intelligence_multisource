import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from io import BytesIO
import sqlite3
import pandas as pd

from data_sources import SourceDataError, classify_columns, prepare_data, read_csv_data, read_sqlite_data

class DataSourceTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame([{
            "date": "2026-01-15", "region": "Northeast", "platform": "Cable TV",
            "network": "ESPN", "program": "NBA Game", "genre": "Sports",
            "viewers": 100, "impressions": 120, "rating_pct": 1.5,
            "ad_spend_usd": 1000, "watch_minutes": 3400,
        }])

    def test_csv(self):
        data = self.frame.to_csv(index=False).encode('utf-8')
        result = prepare_data(read_csv_data(data), 'CSV')
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['program'], 'NBA Game')

    def test_header_normalization(self):
        frame = self.frame.rename(columns={'rating_pct': 'Rating Pct'})
        result = prepare_data(frame, 'Test')
        self.assertIn('rating_pct', result.columns)

    def test_flexible_schema_and_aliases(self):
        frame = pd.DataFrame({
            'Event Date': ['31/01/2026', '01/02/2026'],
            'Market': ['North', 'South'],
            'Audience Size': ['1.2M', '950K'],
            'Revenue USD': ['$2,500.50', '$3,100.00'],
            'Campaign Name': ['Launch', 'Launch'],
        })
        result = prepare_data(frame, 'Flexible')
        schema = classify_columns(result)
        self.assertIn('date', schema['dates'])
        self.assertIn('viewers', schema['numerics'])
        self.assertIn('revenue_usd', schema['numerics'])
        self.assertIn('campaign_name', schema['dimensions'])
        self.assertEqual(result['viewers'].iloc[0], 1_200_000)
        self.assertEqual(result['revenue_usd'].iloc[0], 2_500.50)

    def test_unknown_metric_is_preserved(self):
        frame = pd.DataFrame({
            'Recorded At': ['2026-03-01', '2026-03-02'],
            'Customer Segment': ['A', 'B'],
            'Conversion Value': ['10.5%', '12.0%'],
        })
        result = prepare_data(frame, 'Custom')
        self.assertIn('conversion_value', classify_columns(result)['numerics'])
        self.assertEqual(result['conversion_value'].iloc[0], 10.5)

    def test_source_without_numeric_metric_is_rejected(self):
        frame = pd.DataFrame({'Name': ['A'], 'Category': ['B']})
        with self.assertRaisesRegex(SourceDataError, 'No numeric metric'):
            prepare_data(frame, 'Broken')

    def test_csv_auto_detects_delimiter_and_encoding(self):
        data = 'Caf\xe9;Amount\nNews;1,250\n'.encode('cp1252')
        result = read_csv_data(data)
        self.assertEqual(list(result.columns), ['Caf\xe9', 'Amount'])

    def test_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'ratings.db')
            with closing(sqlite3.connect(db)) as conn:
                self.frame.to_sql('ratings', conn, index=False)
            result = prepare_data(read_sqlite_data(db, 'ratings', 100), 'SQL')
            self.assertEqual(result['viewers'].iloc[0], 100)

    def test_sqlite_identifier_validation(self):
        with self.assertRaisesRegex(SourceDataError, 'Invalid table name'):
            read_sqlite_data('none.db', 'ratings; DROP TABLE ratings', 20)

    def test_nielsen_report_with_title_and_footer(self):
        content = (
            'Report Title (12345)\n\n'
            '"Geography","Viewing Source","Program","Dates","RTG % (X.X)","SHR %","IMP (000)"\n'
            '"New Orleans","WVUE-DT 7.1","Pelicans Game","10/22/2026","0.4","2","3"\n'
            '"New Orleans","WVUE-DT 7.1","Pelicans Game","10/24/2026","0.1","0","0"\n\n'
            '"Copyright (c) 2026 The Nielsen Company. All rights reserved."\n'
            'Report Name:,,Sample,,,,,\n'
        ).encode('utf-8')
        raw = read_csv_data(content)
        self.assertEqual(len(raw), 2)
        prepared = prepare_data(raw, 'Nielsen Test')
        schema = classify_columns(prepared)
        self.assertIn('date', schema['dates'])
        self.assertIn('region', schema['dimensions'])
        self.assertIn('rating_pct', schema['numerics'])
        self.assertIn('impressions', schema['numerics'])
        self.assertIn('shr', schema['numerics'])
        self.assertEqual(prepared['rating_pct'].iloc[0], 0.4)
        self.assertEqual(prepared['impressions'].iloc[0], 3)

    def test_value_based_date_and_identifier_detection(self):
        frame = pd.DataFrame({
            'airing_slot': ['2026-05-01', '2026-05-08'],
            'customer_id': [1001, 1002],
            'empty_col': [None, None],
            'total_sales': ['$1,500', '$2,300'],
        })
        prepared = prepare_data(frame, 'AutoDetect')
        schema = classify_columns(prepared)
        self.assertIn('airing_slot', schema['dates'])
        self.assertIn('total_sales', schema['numerics'])
        self.assertIn('customer_id', schema['dimensions'])
        self.assertNotIn('customer_id', schema['numerics'])
        self.assertNotIn('empty_col', schema['numerics'])
        self.assertNotIn('empty_col', schema['dimensions'])

if __name__ == '__main__':
    unittest.main()
