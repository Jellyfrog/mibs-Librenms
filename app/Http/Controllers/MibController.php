<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;

class MibController extends Controller
{
    /**
     * Display a listing of the resource.
     *
     * @return \Illuminate\Http\Response
     */
    public function index()
    {
        $data = json_decode(Storage::get('mib_out3/index.json'), true);
        $data = $data['oids'];

        ksort($data, SORT_NATURAL);

        return view('index', ['mibs' => $data]);
    }



    /**
     * Store a newly created resource in storage.
     *
     * @param  \Illuminate\Http\Request  $request
     * @return \Illuminate\Http\Response
     */
    public function mib(Request $request, string $mib)
    {
        try {
            $input = json_decode(Storage::get("mib_out3/${mib}.json"));
        } catch(\Exception $e) {
            abort('404');
        }

        $indent = 0;
        $data = [];
        $moduleidentity = null;
        $textualconvention = [];
        $imports = [];

        foreach($input as $name => &$d) {
            switch($name) {
                case "imports":
                    unset($d->class);
                    $imports = &$d;

                    break;
                case "meta":
                    break;
                default:

                    switch($d->class) {
                        case "textualconvention":
                            $textualconvention[] = &$d;
                            break;
                        case "moduleidentity":
                            $moduleidentity = &$d;
                            break;
                        default:

                            if(self::isCollapsable($d)) {
                                $d->collapsable = true;
                            }

                            if(isset($d->status)) {
                                $d->statusIcon = self::getStatusIcon($d->status);
                            }

                            $data[$d->oid] = &$d;
                            break;
                    }
                    break;
            }
        }

        ksort($data, SORT_NATURAL);

        return view('mib', compact('mib', 'indent' ,'data', 'moduleidentity', 'imports'));
    }


    private static function isCollapsable($data): bool {
/*
        if(in_array($data->class, ["objectidentity"])) {
            return true;
        }
*/
        if(!isset($data->nodetype)) {
            return false;
        }

        if(in_array($data->nodetype, ["table"])) {
            return true;
        }

        return false;
    }

    private static function getStatusIcon($status): ?string {
        switch($status) {
            case "deprecated":
                return "exclamation.svg";
                break;
        }

        return null;
    }
}
