-- Most recent reading per city (refreshed every hour)

with latest as (
    select
        city_name,
        state_code,
        observed_at,
        row_number() over (
            partition by city_name, state_code
            order by observed_at desc
        ) as rn
    from {{ ref('stg_weather_raw') }}
),

current_readings as (
    select s.*
    from {{ ref('stg_weather_raw') }} s
    inner join latest l
        on s.city_name = l.city_name
        and s.state_code = l.state_code
        and s.observed_at = l.observed_at
    where l.rn = 1
)

select
    city_name,
    state_code,
    country_code,
    latitude,
    longitude,
    observed_at,
    temp_f,
    feels_like_f,
    temp_min_f,
    temp_max_f,
    humidity_pct,
    pressure_hpa,
    visibility_m,
    wind_speed_mph,
    wind_gust_mph,
    clouds_pct,
    condition_main,
    condition_description
from current_readings
