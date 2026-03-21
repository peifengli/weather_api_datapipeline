-- Staging model: reads raw weather JSON files ingested into Athena external table
-- Normalizes column names and casts types for downstream marts

with source as (
    select * from {{ source('weather_raw', 'weather') }}
),

renamed as (
    select
        city                                        as city_name,
        state                                       as state_code,
        country                                     as country_code,
        cast(lat as double)                         as latitude,
        cast(lon as double)                         as longitude,
        cast(observed_at as timestamp)              as observed_at,
        cast(fetched_at as timestamp)               as fetched_at,

        -- Temperature (°F)
        cast(temp_f as double)                      as temp_f,
        cast(feels_like_f as double)                as feels_like_f,
        cast(temp_min_f as double)                  as temp_min_f,
        cast(temp_max_f as double)                  as temp_max_f,

        -- Atmosphere
        cast(humidity_pct as int)                   as humidity_pct,
        cast(pressure_hpa as int)                   as pressure_hpa,
        cast(visibility_m as int)                   as visibility_m,

        -- Wind
        cast(wind_speed_mph as double)              as wind_speed_mph,
        cast(wind_deg as int)                       as wind_deg,
        cast(wind_gust_mph as double)               as wind_gust_mph,

        -- Cloud / condition
        cast(clouds_pct as int)                     as clouds_pct,
        condition_main                              as condition_main,
        condition_description                       as condition_description,
        condition_icon                              as condition_icon,

        -- Derived partitions
        cast(date_trunc('hour', cast(observed_at as timestamp)) as timestamp) as observed_hour

    from source
)

select * from renamed
