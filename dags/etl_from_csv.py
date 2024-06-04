import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from airflow import DAG
from airflow.decorators import task
from airflow.operators.empty import EmptyOperator
from airflow.models import Variable


default_args= {
    'owner': 'Rachman',
    'start_date': datetime(2024, 6, 1)
}

with DAG(
    'etl_csv_files',
    description='from gdrive to postgres',
    schedule_interval='@daily',
    default_args=default_args, 
    catchup=False) as dag:
    files = {
        'customer_interactions' : 'https://drive.google.com/file/d/1qYJCwzPsxPUj1L7sQrTOJrfY_ZbD66Cj/view?usp=sharing',
        'product_details' : 'https://drive.google.com/file/d/1b34akrI0jHzh3m-52FXwRjvWJkpO8MGZ/view?usp=sharing',
        'purchase_history' : 'https://drive.google.com/file/d/1Y5pKT06hroLu9pnXMScWM2RlJlFn6IWS/view?usp=sharing'
    }

    start = EmptyOperator(task_id='start')
    end = EmptyOperator(task_id='end')

    def read_from_gdrive(url,file_name):
        url = 'https://drive.google.com/uc?id=' + url.split('/')[-2]
        df = pd.read_csv(url)
        print("Sample data :")
        print(df.head())
        df.to_csv(f'/opt/airflow/data/{file_name}.csv',index=False)

    @task()
    def get_files_customer():
        file_name = list(files.keys())[0]
        url = files['customer_interactions']
        df = read_from_gdrive(url,file_name)
        return df 

    @task()
    def get_files_product():
        file_name = list(files.keys())[1]
        url = files['product_details']
        df = read_from_gdrive(url,file_name)
        return df
    
    @task()
    def get_files_purchase():
        file_name = list(files.keys())[2]
        url = files['purchase_history']
        df = read_from_gdrive(url,file_name)
        return df

    @task()
    def combine_files():
        # Read the dataframes
        df_customer = pd.read_csv(f'/opt/airflow/data/{list(files.keys())[0]}.csv')
        df_product = pd.read_csv(f'/opt/airflow/data/{list(files.keys())[1]}.csv')
        df_purchase = pd.read_csv(f'/opt/airflow/data/{list(files.keys())[2]}.csv')

        # Join df_customer and df_purchase on 'customer_id'
        df = df_customer.set_index('customer_id').join(df_purchase.set_index('customer_id'), how='inner', lsuffix='_cust', rsuffix='_purch').reset_index()

        # Join the resulting dataframe with df_product on 'product_id'
        df = df.set_index('product_id').join(df_product.set_index('product_id'), how='inner').reset_index()

        print(df.head())
        df.to_csv(f'/opt/airflow/data/data_combine.csv', index=False)
    

    @task()
    def preprocess_data():
        df = pd.read_csv('/opt/airflow/data/data_combine.csv')
        
        # Handle missing values (example: fill missing numeric values with the mean)
        df.fillna(df.mean(numeric_only=True), inplace=True)
        
        # Convert data types if necessary (example: ensure 'purchase_date' is datetime)
        df['purchase_date'] = pd.to_datetime(df['purchase_date'], errors='coerce')
        
        # Remove duplicates if any
        df.drop_duplicates(inplace=True)

        # Any other preprocessing steps can be added here

        print("Preprocessed data is Success")
        print(df.head())
        df.to_csv('/opt/airflow/data/data_combine_preprocessed.csv', index=False)

    @task()
    def insert_to_db():
        database = "data_from_airflow"
        username = "airflow_user"
        password = "airflow_password"
        host = "postgres"

        postgres_url = f"postgresql+psycopg2://{username}:{password}@{host}/{database}"

        engine = create_engine(postgres_url)
        conn = engine.connect()

        df = pd.read_csv('/opt/airflow/data/data_combine_preprocessed.csv')

        df.to_sql('data_customer', conn, index=False, if_exists='replace')
        print("Success INSERT")

    start >> [get_files_customer(), get_files_product(), get_files_purchase()] >> combine_files() >> preprocess_data() >> insert_to_db() >> end