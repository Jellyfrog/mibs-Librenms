<x-app>
    <x-slot name="title">{{ $mib }}</x-slot>
    <x-slot name="header">
        {{ $mib }}
        |
        MIB date: {{ $moduleidentity->lastupdated ?? 'N/A' }}
    </x-slot>

    <div class="flex justify-between flex-row">

        <div class="-my-2 overflow-x-auto sm:-mx-6 lg:-mx-8">
            <div class="py-2 align-middle inline-block min-w-full sm:px-6 lg:px-8">
                <div class="shadow overflow-hidden border-b border-gray-200 sm:rounded-lg">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-100">
                            <tr>
                                <th scope="col" class="px-6 py-1 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    {{ $mib }}
                                </th>
                            </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                            <tr>
                                <td class="px-6 py-1">
                                    {{ $moduleidentity->description ?? 'N/A' }}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="-my-2 overflow-x-auto sm:-mx-6 lg:-mx-8">
            <div class="py-2 align-middle inline-block min-w-full sm:px-6 lg:px-8">
                <div class="shadow overflow-hidden border-b border-gray-200 sm:rounded-lg">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-100">
                            <tr class="text-left text-gray-500 uppercase tracking-wider">
                                <th scope="col" class="px-6 py-1 text-xs font-medium">
                                    Imported Objects
                                </th>
                                <th scope="col" class="px-6 py-1  text-xs font-medium ">MIB</th>
                            </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                            @foreach($imports as $mib => $objects)
                            <tr class="even:bg-gray-50">
                                <td class="px-6 py-1">
                                    {{ implode(", ", $objects) }}
                                </td>
                                <td class="px-6 py-1 whitespace-nowrap">
                                    <div class="text-sm text-gray-900">{{ $mib }}</div>
                                </td>
                            </tr>
                            @endforeach
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

    </div>

    <br>

    <div class="shadow overflow-hidden border-b border-gray-200 sm:rounded-lg">
        <table class="min-w-full divide-y divide-gray-200 bg-white">
            <thead class="bg-gray-100">
                <tr class="text-left text-gray-500 uppercase tracking-wider">
                    <th scope="col" class="py-1 text-xs font-medium">Name</th>
                    {{--<th scope="col" class="px-6 py-1 text-xs font-medium"></th>--}}
                    {{--<th scope="col" class="py-1 text-xs font-medium">Class</th>--}}
                    {{--<th scope="col" class="py-1 text-xs font-medium">Type</th>--}}

                    <th scope="col" class="py-1 text-xs font-medium">Type</th>
                    <th scope="col" class="py-1 text-xs font-medium">Size</th>
                    <th scope="col" class="py-1 text-xs font-medium">R/W</th>
                    <th scope="col" class="py-1 text-xs font-medium">Status</th>
                    <th scope="col" class="py-1 text-xs font-medium">Oid</th>
                </tr>
            </thead>

            @foreach($data as $oid => $data)

                @php
                    $level_current = substr_count($oid, '.') -6;
                @endphp


                @if(isset($level_parents) && $level_current <= end($level_parents))
                    @php
                        array_pop($level_parents);
                    @endphp

                    </tbody>
                @endif

                @if(isset($data->collapsable))
                    @php
                        $level_parents[] = $level_current;
                    @endphp

                    <tbody x-data="{open: true}">
                @endif

                <tr id="{{ $oid }}"
                    class="even:bg-gray-100 hover:bg-gray-200 target:bg-pink-100 @isset($data->collapsable) cursor-pointer @endisset"
                    @isset($data->collapsable)
                        @click="open = ! open"
                    @else
                        x-show="open"
                    @endif
                >

                    <td class="apl-[{{$level_current*2}}px]">
                        {!! str_repeat("&nbsp;&nbsp;&nbsp;&nbsp;", $level_current) !!}

                        <img src="{{ $data->nodetype ?? $data->class ?? 'unknown' }}.svg" class="w-[24px] h-[24px] inline" title="{{ $data->nodetype ?? $data->class ?? null }}" />

                        {{ $data->name }}

                        @isset($data->description)
                            <img src="info.svg" class="w-[16px] h-[16px] inline" title="{{ str_replace('"', '&quote;', $data->description) }}" />
                        @endisset
                    </td>
                    {{--<td class="px-6 py-1 border-r-2 border-black">{{ isset($data->collapsable) ? 'X' : null }}</td>--}}
                    {{--<td class="">{{ $data->class }}</td>--}}
                    {{--<td>{{ $data->nodetype ?? null }}</td>--}}
                    <td>{{ $data->syntax->type ?? null }}</td>
                    <td>
                        @isset($data->syntax->constraints->size[0]->min)
                            {{ $data->syntax->constraints->size[0]->min }}
                            -
                        @endisset
                        {{ $data->syntax->constraints->size[0]->max ?? null }}

                        @isset($data->syntax->constraints->enumeration)
                            <ul>
                            @foreach($data->syntax->constraints->enumeration as $value => $key)
                                <li>{{ $key }} = {{ $value }}</li>
                            @endforeach
                            </ul>
                        @endisset
                    </td>
                    <td>{{ $data->maxaccess ?? null }}</td>
                    <td>
                        @isset($data->statusIcon)
                            <img src="{{ $data->statusIcon }}" class="w-[16px] h-[16px] inline" title="{{ $data->status }}" />
                        @endisset
                    </td>
                    <td><a href="#{{ $oid }}">{{ $oid }}</a></td>
                </tr>

            @endforeach
        </table>
    </div>
</x-app>
