<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="csrf-token" content="{{ csrf_token() }}">

        <title>{{ $title ?? config('app.name', 'LibreNMS') }}</title>

        <!-- Styles -->
        <link rel="stylesheet" href="{{ mix('css/app.css') }}">

        <!-- Scripts -->
        <script src="{{ mix('js/app.js') }}" defer></script>
    </head>
    <body class="font-sans antialiased">
        <div class="min-h-screen bg-gray-100">

            <nav x-data="{ open: false }" class="bg-white border-b border-gray-100">
                <!-- Primary Navigation Menu -->
                <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div class="flex justify-between h-16">
                        <div class="flex">
                            <!-- Logo -->
                            <div class="flex-shrink-0 flex items-center">
                                <a href="{{ route('index') }}">
                                    <img src="logo.svg" class="block h-10 w-auto fill-current text-gray-600" />
                                </a>
                            </div>

                            <!-- Navigation Links -->
                            <div class="hidden space-x-8 sm:-my-px sm:ml-10 sm:flex">
                                <a class="inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium leading-5 text-gray-500">
                                    {{ $header ?? __('Librenms MIB Database') }}
                                </a>
                            </div>
                        </div>

                    </div>
                </div>

                <!-- Responsive Navigation Menu -->
                <div class="sm:hidden">
                    <div class="pt-2 pb-3 space-y-1">
                        <a class="block pl-3 pr-4 py-2 border-l-4 border-transparent text-base font-medium text-gray-600">
                            {{ $header ?? __('Librenms MIB Database') }}
                        </a>
                    </div>

                </div>
            </nav>

            <!-- Page Content -->
            <main>

                <div class="py-5">
                    <div class="max-w-8xl mx-auto sm:px-6 lg:px-8">
                        {{ $slot }}
                    </div>
                </div>
            </main>
        </div>
    </body>
</html>
